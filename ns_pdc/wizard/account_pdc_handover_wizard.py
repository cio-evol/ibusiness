from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
from odoo.tools import float_compare, float_round

import logging
_logger = logging.getLogger(__name__)


class AccountPDCHandoverWizard(models.TransientModel):
    _name = 'account.pdc.handover.wizard'
    _description = 'PDC Handover Wizard'

    pdc_id = fields.Many2one('account.pdc', string='PDC', required=True, readonly=True)
    handover_to_partner_id = fields.Many2one('res.partner', string='Handover To', required=True,
                                           help="The vendor who will receive this cash cheque")
    cheque_amount = fields.Float(string='Cheque Amount', readonly=True)
    total_allocated = fields.Float(string='Total Allocated', compute='_compute_total_allocated', store=True)
    remaining_amount = fields.Float(string='Remaining Amount', compute='_compute_remaining_amount', store=True)
    handover_date = fields.Date(string='Handover Date', default=fields.Date.today, required=True)
    notes = fields.Text(string='Notes')

    allocation_ids = fields.One2many('account.pdc.handover.allocation', 'handover_wizard_id',
                                   string='Bill Allocations')

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        context = self.env.context

        if context.get('default_pdc_id'):
            pdc = self.env['account.pdc'].browse(context['default_pdc_id'])
            res['pdc_id'] = pdc.id
            res['cheque_amount'] = pdc.amount

        return res

    @api.depends('allocation_ids', 'allocation_ids.amount_allocate')
    def _compute_total_allocated(self):
        for record in self:
            record.total_allocated = sum(record.allocation_ids.mapped('amount_allocate'))

    @api.depends('cheque_amount', 'total_allocated')
    def _compute_remaining_amount(self):
        for record in self:
            record.remaining_amount = record.cheque_amount - record.total_allocated

    @api.onchange('handover_to_partner_id')
    def _onchange_handover_to_partner(self):
        """Clear allocations when partner changes"""
        if self.handover_to_partner_id:
            self.allocation_ids = [(5, 0, 0)]  # Clear existing allocations

    def action_confirm(self):
        """Process the handover"""
        self.ensure_one()
        self._validate_handover()

        # If no allocations, handover full amount without specific bill allocations
        if not self.allocation_ids:
            return self._process_handover_without_allocations()

        # Check if there's remaining amount (only relevant when there are allocations)
        if float_compare(self.remaining_amount, 0.01, precision_digits=2) > 0:
            # Show confirmation dialog for remaining amount
            return self._show_remaining_amount_dialog()

        # Process handover with allocations
        return self._process_handover()

    def action_confirm_with_remaining(self):
        """Confirm handover and keep remaining balance open"""
        return self._process_handover(keep_remaining=True)

    def _validate_handover(self):
        """Validate handover data"""
        if self.pdc_id.state != 'confirmed':
            raise UserError(_('PDC must be in confirmed state to process handover.'))

        # Bill allocation is now optional - allow handover without allocations
        # Only validate allocation amounts if allocations exist
        if self.allocation_ids:
            if float_compare(self.total_allocated, 0, precision_digits=2) <= 0:
                raise UserError(_('Total allocated amount must be greater than zero.'))

            if float_compare(self.total_allocated, self.cheque_amount, precision_digits=2) > 0:
                raise UserError(_('Total allocated amount cannot exceed cheque amount.'))

    def _show_remaining_amount_dialog(self):
        """Show confirmation dialog for remaining amount"""
        return {
            'name': _('Remaining Amount Confirmation'),
            'type': 'ir.actions.act_window',
            'res_model': 'account.pdc.handover.confirm',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_handover_wizard_id': self.id,
                'default_remaining_amount': self.remaining_amount,
                'default_handover_to_partner_id': self.handover_to_partner_id.id,
            },
        }

    def _process_handover(self, keep_remaining=False):
        """Process the handover and create payments"""
        # Create vendor payments for each bill allocation
        payments = self._create_handover_payments()

        # Create handover breakdown records
        self._create_handover_breakdown_records()

        # Update PDC with handover information
        payment_ids = [p.id for p in payments]
        self.pdc_id.write({
            'state': 'handover',
            'handover_date': self.handover_date,
            'handover_to_partner_id': self.handover_to_partner_id.id,
            'handover_notes': self.notes,
        })

        # Show result - show list of payments if multiple, form if single
        if len(payments) == 1:
            return {
                'type': 'ir.actions.act_window',
                'name': _('Handover Payment'),
                'res_model': 'account.payment',
                'res_id': payments[0].id,
                'view_mode': 'form',
            }
        else:
            return {
                'type': 'ir.actions.act_window',
                'name': _('Handover Payments'),
                'res_model': 'account.payment',
                'view_mode': 'list,form',
                'domain': [('id', 'in', payment_ids)],
            }

    def _process_handover_without_allocations(self):
        """Process handover without bill allocations - create simple handover payment"""
        # Create simple handover payment without bill allocation
        payment = self._create_simple_handover_payment()

        # Update PDC with handover information (no breakdown records needed)
        self.pdc_id.write({
            'state': 'handover',
            'handover_date': self.handover_date,
            'handover_to_partner_id': self.handover_to_partner_id.id,
            'handover_notes': self.notes,
        })

        # Log the handover
        self.pdc_id.message_post(
            body=_('PDC handed over without bill allocations\nHandover To: %s\nAmount: %.2f\nNotes: %s') % (
                self.handover_to_partner_id.name,
                self.cheque_amount,
                self.notes or 'None'
            ),
            message_type='notification'
        )

        # Show the created payment
        return {
            'type': 'ir.actions.act_window',
            'name': _('Handover Payment'),
            'res_model': 'account.payment',
            'res_id': payment.id,
            'view_mode': 'form',
        }

    def _create_simple_handover_payment(self):
        """Create simple handover payment without specific bill allocations"""
        # Get cheque-in-hand journal
        cheque_journal = self.env['account.journal'].search(
            [('cheque_in_hand', '=', True)], order='id desc', limit=1
        )

        if not cheque_journal:
            raise UserError(_('Cheque-in-hand journal not found.'))

        # Get payment method line
        payment_method_line_id = self._get_payment_method_line_for_journal(
            cheque_journal, 'outbound'
        )

        if not payment_method_line_id:
            raise UserError(_(
                'No payment method line found for outbound payments in cheque-in-hand journal.'
            ))

        # Create payment with full cheque amount (no specific allocations)
        payment_vals = {
            'payment_type': 'outbound',
            'partner_type': 'supplier',
            'partner_id': self.handover_to_partner_id.id,
            'amount': self.cheque_amount,
            'date': self.handover_date,
            'journal_id': cheque_journal.id,
            'payment_method_line_id': payment_method_line_id,
            'memo': _('PDC Handover (No Bill Allocation) - %s - Cheque: %s') % (
                self.pdc_id.name,
                self.pdc_id.cheque_number
            ),
            'pdc_handover_id': self.pdc_id.id,
            'is_handover_payment': True,
        }

        # Create and post payment
        payment = self.env['account.payment'].create(payment_vals)
        payment.action_post()

        # Link handover payment journal entry to PDC for tracking
        if payment.move_id:
            self.pdc_id._link_journal_entries(payment.move_id, "Simple Handover Payment (No Allocations)")

        _logger.info(f"Created simple handover payment {payment.name} for PDC {self.pdc_id.name} without bill allocations")

        return payment

    def _create_handover_payments(self):
        """Create single consolidated payment for full cheque amount"""
        # Get cheque-in-hand journal
        cheque_journal = self.env['account.journal'].search(
            [('cheque_in_hand', '=', True)], order='id desc', limit=1
        )

        if not cheque_journal:
            raise UserError(_('Cheque-in-hand journal not found.'))

        # Get payment method line
        payment_method_line_id = self._get_payment_method_line_for_journal(
            cheque_journal, 'outbound'
        )

        if not payment_method_line_id:
            raise UserError(_(
                'No payment method line found for outbound payments in cheque-in-hand journal.'
            ))

        # Create single consolidated payment
        payment = self._create_consolidated_payment(cheque_journal, payment_method_line_id)

        return [payment]  # Return as list for compatibility

    def _create_consolidated_payment(self, cheque_journal, payment_method_line_id):
        """Create single consolidated payment with simple approach - no manual reconciliation"""

        # Create payment with full cheque amount
        payment_vals = {
            'payment_type': 'outbound',
            'partner_type': 'supplier',
            'partner_id': self.handover_to_partner_id.id,
            'amount': self.cheque_amount,  # Full cheque amount
            'date': self.handover_date,
            'journal_id': cheque_journal.id,
            'payment_method_line_id': payment_method_line_id,
            'memo': _('PDC Handover - %s - Cheque: %s') % (self.pdc_id.name, self.pdc_id.cheque_number),
            'pdc_handover_id': self.pdc_id.id,
            'is_handover_payment': True,
        }

        # Create and post payment
        payment = self.env['account.payment'].create(payment_vals)
        payment.action_post()

        # Link handover payment journal entry to PDC for tracking
        if payment.move_id:
            self.pdc_id._link_journal_entries(payment.move_id, "Handover Payment")

        # Now handle custom reconciliation with specific amounts (using PDC approach)
        self._reconcile_payment_with_specific_amounts(payment)

        return payment

    def _reconcile_payment_with_specific_amounts(self, payment):
        """Reconcile payment with bills using specific allocated amounts (same as PDC logic)"""

        # Get payment's payable line
        payment_lines = payment.move_id.line_ids.filtered(
            lambda l: l.account_id.account_type == 'liability_payable'
            and not l.reconciled
        )

        if not payment_lines:
            raise UserError(_('No payable line found in payment journal entry.'))

        if len(payment_lines) > 1:
            raise UserError(_('Multiple payable lines found in payment. Expected exactly one.'))

        payment_line = payment_lines[0]
        remaining_payment_amount = abs(payment_line.amount_residual)

        # Create partial reconciliation for each bill allocation
        for alloc in self.allocation_ids:
            bill = alloc.bill_id
            allocated_amount = alloc.amount_allocate

            # Get bill payable lines
            bill_lines = bill.line_ids.filtered(
                lambda l: l.account_id == payment_line.account_id  # Same account required
                and not l.reconciled
                and l.amount_residual != 0
            )

            if not bill_lines:
                continue

            # Get the first unreconciled line
            bill_line = bill_lines[0]

            # Validate allocation amount
            max_reconcilable = min(remaining_payment_amount, abs(bill_line.amount_residual))
            if allocated_amount > max_reconcilable:
                allocated_amount = max_reconcilable

            if allocated_amount <= 0:
                continue

            # Create partial reconciliation using the same method as PDC
            self._create_partial_reconciliation(payment_line, bill_line, allocated_amount)
            remaining_payment_amount -= allocated_amount

            if remaining_payment_amount <= 0.01:  # Small tolerance for rounding
                break

    def _create_partial_reconciliation(self, payment_line, bill_line, amount):
        """Create a partial reconciliation between payment line and bill line (copied from PDC logic)"""

        # Determine which line is debit and which is credit
        if payment_line.balance > 0:
            debit_line = payment_line
            credit_line = bill_line
            debit_amount_currency = amount if payment_line.currency_id else 0
            credit_amount_currency = amount if bill_line.currency_id else 0
        else:
            debit_line = bill_line
            credit_line = payment_line
            debit_amount_currency = amount if bill_line.currency_id else 0
            credit_amount_currency = amount if payment_line.currency_id else 0

        # Create the partial reconciliation record
        partial_reconcile_vals = {
            'debit_move_id': debit_line.id,
            'credit_move_id': credit_line.id,
            'amount': amount,
            'debit_amount_currency': debit_amount_currency,
            'credit_amount_currency': credit_amount_currency,
            'debit_currency_id': debit_line.currency_id.id if debit_line.currency_id else False,
            'credit_currency_id': credit_line.currency_id.id if credit_line.currency_id else False,
        }

        try:
            partial_reconcile = self.env['account.partial.reconcile'].create(partial_reconcile_vals)
            _logger.info(
                'Created partial reconciliation between payment line %s and bill line %s for amount %.2f',
                payment_line.id, bill_line.id, amount
            )
            return partial_reconcile
        except Exception as e:
            _logger.error('Failed to create partial reconciliation: %s', str(e))
            raise UserError(_('Failed to create partial reconciliation: %s') % str(e))

    def _create_handover_breakdown_records(self):
        """Create handover breakdown records for tracking allocations"""
        breakdown_vals = []
        for alloc in self.allocation_ids:
            breakdown_vals.append({
                'pdc_id': self.pdc_id.id,
                'bill_id': alloc.bill_id.id,
                'amount_allocate': alloc.amount_allocate,
            })

        if breakdown_vals:
            self.env['account.pdc.handover.breakdown'].create(breakdown_vals)

    def _get_payment_method_line_for_journal(self, journal, payment_type):
        """Get appropriate payment method line for a specific journal"""
        if not journal:
            return False

        # Get the appropriate method lines based on payment type
        method_lines = (journal.inbound_payment_method_line_ids
                       if payment_type == 'inbound'
                       else journal.outbound_payment_method_line_ids)

        # Try to find 'manual' payment method first
        manual_method = method_lines.filtered(lambda x: x.code == 'manual')
        if manual_method:
            return manual_method[0].id

        # Fallback: return first available method
        if method_lines:
            return method_lines[0].id

        return False


class AccountPDCHandoverAllocation(models.TransientModel):
    _name = 'account.pdc.handover.allocation'
    _description = 'PDC Handover Allocation'

    handover_wizard_id = fields.Many2one('account.pdc.handover.wizard',
                                        required=True, ondelete='cascade')
    bill_id = fields.Many2one('account.move', string='Vendor Bill', required=True,
                             domain="[('move_type', '=', 'in_invoice'), ('state', '=', 'posted'), "
                                    "('payment_state', 'in', ('not_paid', 'partial')), "
                                    "('partner_id', '=', parent.handover_to_partner_id)]")
    amount = fields.Float(string='Bill Amount', compute='_compute_amount', store=True)
    amount_allocate = fields.Float(string='Amount to Allocate', required=True)

    @api.depends('bill_id')
    def _compute_amount(self):
        for record in self:
            record.amount = record.bill_id.amount_residual if record.bill_id else 0.0

    @api.onchange('bill_id')
    def _onchange_bill_id(self):
        if self.bill_id and self.bill_id.amount_residual > 0:
            self.amount_allocate = self.bill_id.amount_residual

    @api.constrains('amount_allocate', 'bill_id')
    def _check_amount_allocate(self):
        for record in self:
            if record.amount_allocate <= 0:
                raise ValidationError(_('Allocated amount must be greater than zero.'))

            if record.bill_id and record.amount_allocate > record.bill_id.amount_residual:
                raise ValidationError(
                    _('Allocated amount (%.2f) cannot exceed bill residual amount (%.2f) for bill %s.') %
                    (record.amount_allocate, record.bill_id.amount_residual, record.bill_id.name)
                )


class AccountPDCHandoverConfirm(models.TransientModel):
    _name = 'account.pdc.handover.confirm'
    _description = 'PDC Handover Remaining Amount Confirmation'

    handover_wizard_id = fields.Many2one('account.pdc.handover.wizard', required=True)
    remaining_amount = fields.Float(string='Remaining Amount', readonly=True)
    handover_to_partner_id = fields.Many2one('res.partner', string='Handover To', readonly=True)

    def action_confirm_with_remaining(self):
        """Confirm handover and keep remaining balance open"""
        return self.handover_wizard_id.action_confirm_with_remaining()

    def action_cancel(self):
        """Cancel and go back to handover wizard"""
        return {
            'type': 'ir.actions.act_window',
            'name': _('PDC Handover'),
            'res_model': 'account.pdc.handover.wizard',
            'res_id': self.handover_wizard_id.id,
            'view_mode': 'form',
            'target': 'new',
        }