from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError


class AccountPDCAllocationWizard(models.TransientModel):
    _name = 'account.pdc.allocation.wizard'
    _description = 'PDC Invoice Allocation Wizard'

    pdc_id = fields.Many2one('account.pdc', string='PDC', required=True, readonly=True)
    partner_id = fields.Many2one(related='pdc_id.partner_id', string='Partner', readonly=True)
    pdc_amount = fields.Float(related='pdc_id.amount', string='PDC Amount', readonly=True)
    already_allocated = fields.Float(string='Already Allocated', compute='_compute_allocated_amounts', store=True)
    available_amount = fields.Float(string='Available Amount', compute='_compute_allocated_amounts', store=True)
    move_type = fields.Selection(related='pdc_id.move_type', string='Type', readonly=True)

    allocation_line_ids = fields.One2many(
        'account.pdc.allocation.wizard.line', 'wizard_id',
        string='Invoice Allocations'
    )
    total_allocation = fields.Float(
        string='Total Allocation',
        compute='_compute_total_allocation',
        store=True
    )

    @api.depends('pdc_id.account_pdc_allocation_ids.amount_allocate', 'pdc_id.account_payment_ids.move_id.line_ids.amount_residual')
    def _compute_allocated_amounts(self):
        for wizard in self:
            wizard.already_allocated = sum(wizard.pdc_id.account_pdc_allocation_ids.mapped('amount_allocate'))

            # Calculate available amount based on actual payment residual, not PDC amount
            actual_payment_residual = wizard._get_payment_residual_amount()
            if actual_payment_residual is not None:
                wizard.available_amount = actual_payment_residual
            else:
                # Fallback to PDC amount if no payment found
                wizard.available_amount = wizard.pdc_amount - wizard.already_allocated

    @api.depends('allocation_line_ids.amount_allocate')
    def _compute_total_allocation(self):
        for wizard in self:
            wizard.total_allocation = sum(wizard.allocation_line_ids.mapped('amount_allocate'))

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        context = self.env.context

        pdc_id = context.get('default_pdc_id')
        if pdc_id:
            pdc = self.env['account.pdc'].browse(pdc_id)
            res['pdc_id'] = pdc_id

            # Get available invoices for this partner
            domain = [
                ('partner_id', '=', pdc.partner_id.id),
                ('state', '=', 'posted'),
                ('payment_state', 'in', ('not_paid', 'partial')),
                ('amount_residual', '>', 0.01)
            ]

            if pdc.move_type == 'out_invoice':
                domain.append(('move_type', 'in', ('out_invoice', 'out_refund')))
            else:
                domain.append(('move_type', 'in', ('in_invoice', 'in_refund')))

            invoices = self.env['account.move'].search(domain, limit=20)

            # Create default allocation lines for available invoices
            allocation_lines = []
            for invoice in invoices:
                allocation_lines.append((0, 0, {
                    'invoice_id': invoice.id,
                    'invoice_amount': invoice.amount_residual,
                    'amount_allocate': 0.0,  # User needs to enter amount
                }))

            res['allocation_line_ids'] = allocation_lines

        return res

    def _get_payment_residual_amount(self):
        """Get the actual residual amount from the PDC payment"""
        for payment in self.pdc_id.account_payment_ids:
            if payment.state in ('in_process', 'paid'):
                # Find unreconciled receivable/payable lines
                unreconciled_lines = payment.move_id.line_ids.filtered(
                    lambda l: l.account_id.account_type in ('asset_receivable', 'liability_payable')
                    and not l.reconciled
                    and abs(l.amount_residual) >= 0.01
                )

                if unreconciled_lines:
                    # Return the total residual amount of unreconciled lines
                    return sum(abs(line.amount_residual) for line in unreconciled_lines)

        return None  # No payment or no unreconciled amount found

    def action_allocate(self):
        """Process the allocation and create PDC allocation records"""
        self.ensure_one()

        if not self.allocation_line_ids:
            raise UserError(_('Please add at least one allocation.'))

        # Get the actual payment residual for validation
        actual_available_amount = self._get_payment_residual_amount()
        if actual_available_amount is None:
            raise UserError(_('No unreconciled payment found for this PDC. Please confirm the PDC first.'))

        # Validate total allocation against actual payment residual
        if self.total_allocation > actual_available_amount:
            raise UserError(_(
                'Total allocation (%.2f) cannot exceed actual payment residual amount (%.2f).\n\n'
                'Payment residual: %.2f\n'
                'You can only allocate up to the remaining unreconciled payment amount.'
            ) % (self.total_allocation, actual_available_amount, actual_available_amount))

        # Validate individual allocations
        for line in self.allocation_line_ids:
            if line.amount_allocate > 0:
                # Recompute invoice amount to ensure it's current
                current_residual = line.invoice_id.amount_residual
                if line.amount_allocate > current_residual:
                    raise UserError(_(
                        'Allocation amount (%.2f) cannot exceed invoice residual amount (%.2f) for %s.\n'
                        'Stored amount: %.2f, Current residual: %.2f'
                    ) % (line.amount_allocate, current_residual, line.invoice_id.name, line.invoice_amount, current_residual))

        # Create PDC allocation records (only for non-zero allocations)
        allocations_created = []
        for line in self.allocation_line_ids:
            if line.amount_allocate > 0:
                # Use the current invoice residual amount, not the stored amount
                current_invoice_amount = line.invoice_id.amount_residual
                allocation = self.env['account.pdc.allocation'].create({
                    'pdc_id': self.pdc_id.id,
                    'invoice_id': line.invoice_id.id,
                    'partner_id': self.partner_id.id,
                    'amount': current_invoice_amount,
                    'amount_allocate': line.amount_allocate,
                })
                allocations_created.append(allocation.id)

        if not allocations_created:
            raise UserError(_('Please enter allocation amounts for at least one invoice.'))

        # Now reconcile using Odoo's standard partial reconciliation approach
        try:
            self._reconcile_using_odoo_standard_approach(allocations_created)
        except Exception as e:
            # If reconciliation fails, the allocations are still created
            import logging
            _logger = logging.getLogger(__name__)
            _logger.warning(f"Auto-reconciliation failed: {str(e)}. Allocations created successfully.")

        # Show success message
        message = _('%d invoice(s) allocated successfully.\n\nAllocations created in PDC record.') % len(allocations_created)
        if self.total_allocation < self.available_amount:
            remaining = self.available_amount - self.total_allocation
            message += _('\nRemaining amount: %.2f available for future allocations.') % remaining

        # Add guidance for manual reconciliation
        message += _('\n\nTo complete the process:\n1. Visit PDC → Payments smart button\n2. Open the payment and use "Reconcile" to match with invoices\n3. This will properly link payment amounts to specific invoices')

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Allocation Complete'),
                'message': message,
                'type': 'success',
                'next': {
                    'type': 'ir.actions.act_window_close'
                }
            }
        }

    def _reconcile_payment_with_allocations(self, allocation_ids):
        """Reconcile the PDC payment with allocated invoices (partial reconciliation)"""
        allocations = self.env['account.pdc.allocation'].browse(allocation_ids)

        # Find the unallocated payment
        unallocated_payment = None
        for payment in self.pdc_id.account_payment_ids:
            if payment.state in ('in_process', 'paid') and payment.move_id:
                payment_lines = payment.move_id.line_ids.filtered(
                    lambda l: l.account_id.account_type in ('asset_receivable', 'liability_payable')
                    and not l.reconciled
                    and abs(l.amount_residual) > 0.01
                )
                if payment_lines:
                    unallocated_payment = payment
                    break

        if not unallocated_payment:
            raise UserError(_('No unallocated payment found for reconciliation.'))

        # Get payment's receivable/payable line
        payment_lines = unallocated_payment.move_id.line_ids.filtered(
            lambda l: l.account_id.account_type in ('asset_receivable', 'liability_payable')
            and not l.reconciled
            and abs(l.amount_residual) > 0.01
        )

        if not payment_lines:
            raise UserError(_('No unreconciled lines found in payment journal entry.'))

        payment_line = payment_lines[0]  # Take the first unreconciled line

        # Reconcile with each allocated invoice (only those with amount > 0)
        for allocation in allocations:
            if allocation.amount_allocate <= 0:
                continue  # Skip zero allocations

            invoice = allocation.invoice_id
            invoice_lines = invoice.line_ids.filtered(
                lambda l: l.account_id.account_type in ('asset_receivable', 'liability_payable')
                and not l.reconciled
                and abs(l.amount_residual) >= 0.01
            )

            if not invoice_lines:
                continue  # Skip if no unreconciled invoice lines

            invoice_line = invoice_lines[0]  # Take first unreconciled line

            # Ensure we don't exceed available amounts
            max_reconcile_amount = min(
                abs(payment_line.amount_residual),
                abs(invoice_line.amount_residual),
                allocation.amount_allocate
            )

            if max_reconcile_amount < 0.01:
                continue  # Skip if amount too small

            try:
                # Create partial reconciliation with proper debit/credit assignment
                if payment_line.account_id == invoice_line.account_id:
                    # Same account - determine debit/credit based on balance
                    if payment_line.balance * invoice_line.balance < 0:  # Opposite signs
                        debit_line = payment_line if payment_line.balance > 0 else invoice_line
                        credit_line = invoice_line if payment_line.balance > 0 else payment_line
                    else:
                        continue  # Same sign balances cannot be reconciled

                    self.env['account.partial.reconcile'].create({
                        'debit_move_id': debit_line.id,
                        'credit_move_id': credit_line.id,
                        'amount': max_reconcile_amount,
                    })

            except Exception as e:
                # Log the error but don't fail the entire allocation
                import logging
                _logger = logging.getLogger(__name__)
                _logger.warning(f"Failed to reconcile payment line {payment_line.id} with invoice line {invoice_line.id}: {str(e)}")
                # Continue with other allocations

    def _safe_reconcile_payment_with_allocations(self, allocation_ids):
        """Safer reconciliation method using Odoo's reconciliation API"""
        allocations = self.env['account.pdc.allocation'].browse(allocation_ids)

        # Find the unallocated payment
        unallocated_payment = None
        for payment in self.pdc_id.account_payment_ids:
            if payment.state in ('in_process', 'paid') and payment.move_id:
                # Check if payment has unreconciled lines
                unreconciled_lines = payment.move_id.line_ids.filtered(
                    lambda l: l.account_id.account_type in ('asset_receivable', 'liability_payable')
                    and not l.reconciled
                )
                if unreconciled_lines:
                    unallocated_payment = payment
                    break

        if not unallocated_payment:
            return  # No unallocated payment found, skip reconciliation

        # Get payment lines that can be reconciled
        payment_lines = unallocated_payment.move_id.line_ids.filtered(
            lambda l: l.account_id.account_type in ('asset_receivable', 'liability_payable')
            and not l.reconciled
        )

        if not payment_lines:
            return  # No lines to reconcile

        # For each allocation, try to reconcile using Odoo's reconciliation methods
        for allocation in allocations:
            if allocation.amount_allocate <= 0:
                continue

            invoice = allocation.invoice_id

            # Get invoice lines that can be reconciled
            invoice_lines = invoice.line_ids.filtered(
                lambda l: l.account_id.account_type in ('asset_receivable', 'liability_payable')
                and not l.reconciled
                and l.partner_id == self.partner_id
            )

            if not invoice_lines:
                continue

            # Try to reconcile using move line reconciliation
            for payment_line in payment_lines:
                for invoice_line in invoice_lines:
                    if (payment_line.account_id == invoice_line.account_id and
                        payment_line.partner_id == invoice_line.partner_id):

                        try:
                            # Check if both lines have residual amounts
                            if (abs(payment_line.amount_residual) < 0.01 or
                                abs(invoice_line.amount_residual) < 0.01):
                                continue

                            # Use partial reconciliation for specific amounts
                            # Determine the correct amount to reconcile
                            reconcile_amount = min(
                                abs(payment_line.amount_residual),
                                abs(invoice_line.amount_residual),
                                allocation.amount_allocate
                            )

                            if reconcile_amount < 0.01:
                                continue

                            # Create partial reconciliation with proper debit/credit assignment
                            partial_reconcile_vals = {
                                'amount': reconcile_amount,
                            }

                            # Determine debit and credit lines based on account balance
                            if payment_line.balance > 0:  # Payment line is debit
                                partial_reconcile_vals.update({
                                    'debit_move_id': payment_line.id,
                                    'credit_move_id': invoice_line.id,
                                })
                            else:  # Payment line is credit
                                partial_reconcile_vals.update({
                                    'debit_move_id': invoice_line.id,
                                    'credit_move_id': payment_line.id,
                                })

                            # Create the partial reconciliation
                            partial_reconcile = self.env['account.partial.reconcile'].create(partial_reconcile_vals)

                            # Log successful reconciliation
                            import logging
                            _logger = logging.getLogger(__name__)
                            _logger.info(f"Successfully created partial reconciliation: {reconcile_amount} between payment {payment_line.id} and invoice {invoice_line.id}")

                            # Break after first successful reconciliation for this allocation
                            break

                        except Exception as e:
                            # Log but continue with other reconciliations
                            import logging
                            _logger = logging.getLogger(__name__)
                            _logger.warning(f"Failed to reconcile lines {payment_line.id} and {invoice_line.id}: {str(e)}")
                            continue

                # Break if we successfully created a reconciliation
                else:
                    continue
                break

    def _reconcile_using_odoo_standard_approach(self, allocation_ids):
        """Use Odoo's standard reconciliation approach similar to payment register"""
        allocations = self.env['account.pdc.allocation'].browse(allocation_ids)

        # Find the payment that needs to be reconciled
        payment = None
        for pmt in self.pdc_id.account_payment_ids:
            if pmt.state in ('in_process', 'paid') and not pmt.is_reconciled:
                payment = pmt
                break

        if not payment:
            return  # No payment to reconcile

        # Group allocations by invoice (should be 1:1 but good practice)
        invoice_allocations = {}
        for allocation in allocations:
            if allocation.amount_allocate > 0:
                invoice = allocation.invoice_id
                if invoice.id not in invoice_allocations:
                    invoice_allocations[invoice.id] = {
                        'invoice': invoice,
                        'total_allocation': 0.0
                    }
                invoice_allocations[invoice.id]['total_allocation'] += allocation.amount_allocate

        # Process each invoice
        for invoice_data in invoice_allocations.values():
            invoice = invoice_data['invoice']
            allocation_amount = invoice_data['total_allocation']

            try:
                # Use the same approach as payment register
                self._reconcile_payment_with_invoice_partial(payment, invoice, allocation_amount)
            except Exception as e:
                import logging
                _logger = logging.getLogger(__name__)
                _logger.warning(f"Failed to reconcile payment {payment.id} with invoice {invoice.id}: {str(e)}")
                continue

    def _reconcile_payment_with_invoice_partial(self, payment, invoice, amount):
        """Reconcile payment with invoice for specific amount using proper partial reconciliation"""

        # Get the payment lines (receivable/payable)
        payment_lines = payment.move_id.line_ids.filtered(
            lambda l: l.account_id.account_type in ('asset_receivable', 'liability_payable')
            and not l.reconciled
            and abs(l.amount_residual) >= 0.01
        )

        # Get the invoice lines (receivable/payable)
        invoice_lines = invoice.line_ids.filtered(
            lambda l: l.account_id.account_type in ('asset_receivable', 'liability_payable')
            and not l.reconciled
            and abs(l.amount_residual) >= 0.01
        )

        if not payment_lines or not invoice_lines:
            return

        payment_line = payment_lines[0]
        invoice_line = invoice_lines[0]

        # Check if they can be reconciled (same account, same partner)
        if (payment_line.account_id != invoice_line.account_id or
            payment_line.partner_id != invoice_line.partner_id):
            return

        # Calculate the amount to reconcile
        reconcile_amount = min(
            abs(payment_line.amount_residual),
            abs(invoice_line.amount_residual),
            amount
        )

        if reconcile_amount < 0.01:
            return

        # Determine which line is debit and which is credit
        # Payment line with positive balance is debit, negative is credit
        if payment_line.balance > 0:  # Payment is debit
            debit_line = payment_line
            credit_line = invoice_line
        else:  # Payment is credit
            debit_line = invoice_line
            credit_line = payment_line

        # Calculate currency amounts
        company_currency = self.env.company.currency_id

        # For debit line currency amount
        if debit_line.currency_id and debit_line.currency_id != company_currency:
            debit_amount_currency = reconcile_amount * (abs(debit_line.amount_currency) / abs(debit_line.balance)) if debit_line.balance else reconcile_amount
        else:
            debit_amount_currency = reconcile_amount

        # For credit line currency amount
        if credit_line.currency_id and credit_line.currency_id != company_currency:
            credit_amount_currency = reconcile_amount * (abs(credit_line.amount_currency) / abs(credit_line.balance)) if credit_line.balance else reconcile_amount
        else:
            credit_amount_currency = reconcile_amount

        # Create the partial reconciliation record
        partial_reconcile_vals = {
            'debit_move_id': debit_line.id,
            'credit_move_id': credit_line.id,
            'amount': reconcile_amount,
            'debit_amount_currency': debit_amount_currency,
            'credit_amount_currency': credit_amount_currency,
        }

        try:
            partial_reconcile = self.env['account.partial.reconcile'].create(partial_reconcile_vals)

            import logging
            _logger = logging.getLogger(__name__)
            _logger.info(f"Created partial reconciliation: {reconcile_amount} between payment line {payment_line.id} and invoice line {invoice_line.id}")

        except Exception as e:
            import logging
            _logger = logging.getLogger(__name__)
            _logger.error(f"Failed to create partial reconciliation: {str(e)}")
            raise


class AccountPDCAllocationWizardLine(models.TransientModel):
    _name = 'account.pdc.allocation.wizard.line'
    _description = 'PDC Allocation Wizard Line'

    wizard_id = fields.Many2one('account.pdc.allocation.wizard', required=True, ondelete='cascade')
    invoice_id = fields.Many2one('account.move', string='Invoice', required=True)
    invoice_amount = fields.Float(string='Invoice Amount', compute='_compute_invoice_amount', store=True, readonly=True)
    amount_allocate = fields.Float(string='Amount to Allocate', required=True)

    @api.depends('invoice_id')
    def _compute_invoice_amount(self):
        for line in self:
            if line.invoice_id:
                line.invoice_amount = line.invoice_id.amount_residual
            else:
                line.invoice_amount = 0.0

    @api.constrains('amount_allocate', 'invoice_amount')
    def _check_allocation_amount(self):
        for line in self:
            if line.amount_allocate < 0:
                raise ValidationError(_('Allocation amount must be positive.'))

            if line.amount_allocate > line.invoice_amount:
                raise ValidationError(_(
                    'Allocation amount (%.2f) cannot exceed invoice amount (%.2f) for %s.'
                ) % (line.amount_allocate, line.invoice_amount, line.invoice_id.name))

    @api.onchange('invoice_id')
    def _onchange_invoice_id(self):
        if self.invoice_id:
            # The invoice_amount will be computed automatically
            self.amount_allocate = 0.0  # Let user decide the amount