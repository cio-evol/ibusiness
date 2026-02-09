from odoo import models, fields, api, _, Command
from odoo.exceptions import UserError, ValidationError
from odoo.tools import float_compare, float_is_zero

import logging
_logger = logging.getLogger(__name__)


class AccountPDC(models.Model):
    _name = 'account.pdc'
    _description = 'Account PDC'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(string='Name', default=lambda self: _('New'), tracking=True, copy=False, readonly=True)
    partner_id = fields.Many2one('res.partner', string='Partner', tracking=True)
    state = fields.Selection(
        selection=[
            ('draft', "Draft"),
            ('confirmed', "Confirmed"),
            ('deposited', "Deposited"),
            ('realized', "Realized"),
            ('handover', "Handed Over"),
            ('return', "Returned"),
            ('canceled', "Canceled"),
        ],
        string='State', default='draft', readonly=False, copy=False,
    )
    created_date = fields.Date(string='Created Date', default=fields.Date.today, tracking=True)
    reference = fields.Char(string='Reference', tracking=True)
    cheque_number = fields.Char(string='Cheque Number', tracking=True)
    cheque_date = fields.Date(string='Cheque Date', default=fields.Date.today, tracking=True)
    chq_bank_id = fields.Many2one('res.bank', string='Cheque Bank', tracking=True)
    customer_bank_account = fields.Char(string='Customer Bank Account Number', tracking=True,
                                       help="The customer's bank account number from the cheque")
    bank_journal_id = fields.Many2one('account.journal', string='Bank Journal', tracking=True, domain=[('type', '=', 'bank')])
    bank_account_number = fields.Char(string='Bank Account Number', tracking=True)
    deposit_date = fields.Date(string='Deposited Date', tracking=True)
    realization_date = fields.Date(string='Realization Date', tracking=True)
    amount = fields.Float(string='Amount', compute='_compute_amount', store=True, tracking=True)
    manual_amount = fields.Float(string='PDC Amount', tracking=True,
                                help="Manual PDC amount. If set, this will be used instead of allocated amount")
    use_manual_amount = fields.Boolean(string='Use Manual Amount', default=False, tracking=True,
                                      help="Check this to enter PDC amount manually instead of using invoice allocations")
    hand_over_to = fields.Many2one('res.partner', string='Handed Over To', tracking=True)
    account_pdc_allocation_ids = fields.One2many('account.pdc.allocation', 'pdc_id', string='PDC Allocations')

    # Handover related fields
    handover_date = fields.Date(string='Handover Date', tracking=True)
    handover_to_partner_id = fields.Many2one('res.partner', string='Handover To Partner', tracking=True)
    handover_notes = fields.Text(string='Handover Notes')
    handover_payment_id = fields.Many2one('account.payment', string='Handover Payment')
    handover_breakdown_ids = fields.One2many('account.pdc.handover.breakdown', 'pdc_id', string='Handover Breakdown')

    account_payment_ids = fields.One2many('account.payment', 'pdc_id', string='Payments')
    account_payment_count = fields.Integer(string='Account Payment Count', compute='_compute_account_payment_count', store=True, readonly=True,
                                           copy=False)

    # Journal Entry Tracking
    linked_journal_entry_ids = fields.Many2many('account.move', 'pdc_journal_entry_rel', 'pdc_id', 'move_id', string='Linked Journal Entries')
    linked_journal_entry_count = fields.Integer(string='Journal Entry Count', compute='_compute_linked_journal_entry_count', store=True)

    move_type = fields.Selection(
        selection=[
            ('out_invoice', 'Customer Invoice'),
            ('in_invoice', 'Vendor Bill'),
        ],
        string='Type', default='out_invoice'
    )

    journal_entry_count = fields.Integer(
        string='Journal Entry Count',
        compute='_compute_journal_entry_count',
        store=False
    )

    # Allocation tracking for manual amount PDCs
    has_unallocated_amount = fields.Boolean(
        string='Has Unallocated Amount',
        compute='_compute_has_unallocated_amount',
        store=False,
        help="True if this is a manual amount PDC with unallocated payment amount"
    )

    company_id = fields.Many2one('res.company', 'Company', default=lambda self: self.env.company)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('name') or vals['name'] == _('New'):
                if vals.get('move_type'):
                    if vals['move_type'] == 'out_invoice':
                        vals['name'] = self.env['ir.sequence'].next_by_code('pdc.cheque.payment') or _('New')
                    else:
                        vals['name'] = self.env['ir.sequence'].next_by_code('pdc.cheque.bill') or _('New')
        return super().create(vals_list)

    @api.depends('account_pdc_allocation_ids', 'account_pdc_allocation_ids.amount_allocate', 'manual_amount', 'use_manual_amount')
    def _compute_amount(self):
        for record in self:
            if record.use_manual_amount:
                record.amount = record.manual_amount
            else:
                record.amount = sum(line.amount_allocate for line in record.account_pdc_allocation_ids)

    @api.depends('account_payment_ids', 'handover_payment_id')
    def _compute_account_payment_count(self):
        for record in self:
            # Count regular payments (from confirmation) and handover payments
            regular_payments = record.account_payment_ids
            handover_payments = self.env['account.payment'].search([('pdc_handover_id', '=', record.id)])
            all_payments = regular_payments | handover_payments
            record.account_payment_count = len(all_payments)

    @api.depends('linked_journal_entry_ids')
    def _compute_linked_journal_entry_count(self):
        for record in self:
            record.linked_journal_entry_count = len(record.linked_journal_entry_ids)

    def _link_journal_entries(self, journal_entries, entry_type=""):
        """Link journal entries to this PDC for tracking"""
        if not journal_entries:
            return

        # Ensure we have a recordset
        if not isinstance(journal_entries, list):
            journal_entries = [journal_entries]

        # Add to linked entries
        for entry in journal_entries:
            if entry and entry.id:
                self.linked_journal_entry_ids = [(4, entry.id)]
                # Add a note to track the entry type and purpose
                self.message_post(
                    body=_('Linked journal entry: %s (%s) - %s') % (entry.name, entry_type, entry.ref or ''),
                    message_type='notification'
                )

    # ===============================================
    # CONFIRMATION FLOW
    # ===============================================

    def action_confirm(self):
        """Confirm PDC and create payments in cheque-in-hand journal"""
        self.ensure_one()
        self._validate_confirmation()

        self.state = 'confirmed'

        # Create payments using strategy pattern
        handlers = {
            'out_invoice': self._confirm_customer_pdc,
            'in_invoice': self._confirm_vendor_pdc,
        }

        handler = handlers.get(self.move_type)
        if not handler:
            raise UserError(_('Unsupported move type for PDC confirmation.'))

        return handler()

    def _validate_confirmation(self):
        """Centralized validation for PDC confirmation"""
        # Check if customer is blocked for PDC
        if self.partner_id.pdc_blocked:
            raise UserError(_(
                'Customer %s is blocked for PDC transactions.\n'
                'Blocked on: %s\n'
                'Reason: %s\n\n'
                'Please contact your administrator to unblock this customer.'
            ) % (
                self.partner_id.name,
                self.partner_id.pdc_block_date or 'Unknown date',
                self.partner_id.pdc_block_reason or 'No reason specified'
            ))

        # For manual amount PDCs, allocations are not required at confirmation
        if not self.use_manual_amount and not self.account_pdc_allocation_ids:
            raise UserError(_('No allocations found for this PDC.'))

        cheque_journal_id = self.env['account.journal'].search(
            [('cheque_in_hand', '=', True)], order='id desc', limit=1)

        if not cheque_journal_id:
            raise UserError(_('Cheque-in-hand journal is required to confirm the PDC.'))

    def _confirm_customer_pdc(self):
        """Confirm customer PDC - create payment in cheque-in-hand journal"""
        if self.use_manual_amount:
            # Manual amount workflow - create unallocated payment
            return self._create_manual_amount_payment('inbound', 'customer')
        else:
            # Original workflow - create payment with allocations
            allocations = self._get_valid_allocations('out_invoice')
            if not allocations:
                raise UserError(_('No invoice allocations found for this PDC.'))
            return self._create_cheque_payment(allocations, 'inbound', 'customer')

    def _confirm_vendor_pdc(self):
        """Confirm vendor PDC - create payment in cheque-in-hand journal"""
        if self.use_manual_amount:
            # Manual amount workflow - create unallocated payment
            return self._create_manual_amount_payment('outbound', 'supplier')
        else:
            # Original workflow - create payment with allocations
            allocations = self._get_valid_allocations('in_invoice')
            if not allocations:
                raise UserError(_('No vendor bill allocations found for this PDC.'))
            return self._create_cheque_payment(allocations, 'outbound', 'supplier')

    def _create_cheque_payment(self, allocations, payment_type, partner_type):
        """Create payment with proper partial reconciliation using payment register logic"""
        # Get cheque-in-hand journal
        cheque_journal = self.env['account.journal'].search(
            [('cheque_in_hand', '=', True)], order='id desc', limit=1)

        if not cheque_journal:
            raise UserError(_('Cheque-in-hand journal not found.'))

        # Group allocations by partner (should be same but good practice)
        partner_allocations = {}
        for alloc in allocations:
            partner_id = alloc.partner_id.id
            if partner_id not in partner_allocations:
                partner_allocations[partner_id] = self.env['account.pdc.allocation']
            partner_allocations[partner_id] |= alloc

        payments_created = self.env['account.payment']

        # Create separate payment for each partner if multiple partners
        for partner_id, partner_allocs in partner_allocations.items():
            payment = self._create_partner_payment(
                partner_allocs, payment_type, partner_type, cheque_journal
            )
            payments_created |= payment

        return payments_created

    def _create_partner_payment(self, allocations, payment_type, partner_type, cheque_journal):
        """Create payment for a specific partner with proper partial allocation"""

        # Get payment method line for the cheque journal
        payment_method_line_id = self._get_payment_method_line_for_journal(
            cheque_journal, payment_type
        )

        if not payment_method_line_id:
            raise UserError(_(
                'No payment method line found for %s payments in cheque-in-hand journal. '
                'Please configure payment methods for this journal.'
            ) % payment_type)

        # Calculate total amount and prepare data
        total_amount = sum(allocations.mapped('amount_allocate'))
        partner = allocations[0].partner_id

        # Collect invoices and their allocated amounts
        invoice_allocations = []
        for alloc in allocations:
            invoice_allocations.append({
                'invoice': alloc.invoice_id,
                'amount': alloc.amount_allocate,
            })

        # Create payment using proper allocation method
        return self._create_payment_with_allocations(
            partner, total_amount, invoice_allocations, cheque_journal,
            payment_method_line_id, payment_type, partner_type
        )

    def _create_payment_with_allocations(self, partner, total_amount, invoice_allocations,
                                       cheque_journal, payment_method_line_id, payment_type, partner_type):
        """Create payment with custom partial allocation logic"""

        # Create basic payment first
        payment_vals = {
            'payment_type': payment_type,
            'partner_type': partner_type,
            'partner_id': partner.id,
            'amount': total_amount,
            'date': fields.Date.context_today(self),
            'journal_id': cheque_journal.id,
            'payment_method_line_id': payment_method_line_id,
            'memo': _('PDC Payment - %s - Cheque: %s') % (self.name, self.cheque_number),
            'pdc_id': self.id,
            'is_chq_payment': True,
            'chq_number': self.cheque_number,
            'chq_date': self.cheque_date,
            'chq_bank_id': self.chq_bank_id.id if self.chq_bank_id else False,
            'bank_account_number': self.bank_account_number,
            'deposit_date': self.deposit_date,
            'handed_over_to_partner': self.hand_over_to.id if self.hand_over_to else False,
        }

        # Create payment
        payment = self.env['account.payment'].create(payment_vals)

        # Post the payment first to create journal entry
        payment.action_post()

        # Link payment journal entry to PDC for tracking
        if payment.move_id:
            self._link_journal_entries(payment.move_id, "PDC Confirmation Payment")

        # Now handle custom reconciliation with specific amounts
        self._reconcile_payment_with_invoices(payment, invoice_allocations)

        return payment

    def _create_manual_amount_payment(self, payment_type, partner_type):
        """Create unallocated payment for manual amount PDCs"""
        # Get cheque-in-hand journal
        cheque_journal = self.env['account.journal'].search(
            [('cheque_in_hand', '=', True)], order='id desc', limit=1)

        if not cheque_journal:
            raise UserError(_('Cheque-in-hand journal not found.'))

        # Get payment method line
        payment_method_line_id = self._get_payment_method_line_for_journal(cheque_journal, payment_type)

        if not payment_method_line_id:
            method_type = 'inbound' if payment_type == 'inbound' else 'outbound'
            raise UserError(_('No %s payment method found for journal %s.') % (method_type, cheque_journal.name))

        # Create payment values
        payment_vals = {
            'payment_type': payment_type,
            'partner_type': partner_type,
            'partner_id': self.partner_id.id,
            'amount': self.manual_amount,
            'date': fields.Date.context_today(self),
            'journal_id': cheque_journal.id,
            'payment_method_line_id': payment_method_line_id,
            'memo': _('PDC Manual Amount Payment - %s - Cheque: %s') % (self.name, self.cheque_number),
            'pdc_id': self.id,
            'is_chq_payment': True,
            'chq_number': self.cheque_number,
            'chq_date': self.cheque_date,
            'chq_bank_id': self.chq_bank_id.id if self.chq_bank_id else False,
            'bank_account_number': self.bank_account_number,
            'deposit_date': self.deposit_date,
            'handed_over_to_partner': self.hand_over_to.id if self.hand_over_to else False,
        }

        # Create and post payment
        payment = self.env['account.payment'].create(payment_vals)
        payment.action_post()

        # Link payment journal entry to PDC for tracking
        if payment.move_id:
            self._link_journal_entries(payment.move_id, "PDC Manual Amount Confirmation Payment")

        _logger.info(f"Created manual amount payment {payment.id} for PDC {self.name} with amount {self.manual_amount}")

        return payment

    def _reconcile_payment_with_invoices(self, payment, invoice_allocations):
        """Reconcile payment with invoices using specific allocated amounts"""

        # Get payment's receivable/payable line
        payment_lines = payment.move_id.line_ids.filtered(
            lambda l: l.account_id.account_type in ('asset_receivable', 'liability_payable')
            and not l.reconciled
        )

        if not payment_lines:
            raise UserError(_('No receivable/payable line found in payment journal entry.'))

        if len(payment_lines) > 1:
            raise UserError(_('Multiple receivable/payable lines found in payment. Expected exactly one.'))

        payment_line = payment_lines[0]
        remaining_payment_amount = abs(payment_line.amount_residual)

        # Create partial reconciliation for each specific allocation
        for alloc_data in invoice_allocations:
            invoice = alloc_data['invoice']
            allocated_amount = alloc_data['amount']

            # Get invoice receivable/payable lines
            invoice_lines = invoice.line_ids.filtered(
                lambda l: l.account_id == payment_line.account_id  # Same account required
                and not l.reconciled
                and l.amount_residual != 0
            )

            if not invoice_lines:
                _logger.warning('No unreconciled lines found for invoice %s', invoice.name)
                continue

            # Get the first unreconciled line (usually there's only one receivable/payable line per invoice)
            invoice_line = invoice_lines[0]

            # Validate allocation amount
            max_reconcilable = min(remaining_payment_amount, abs(invoice_line.amount_residual))
            if allocated_amount > max_reconcilable:
                _logger.warning(
                    'Allocation amount %.2f exceeds maximum reconcilable amount %.2f for invoice %s',
                    allocated_amount, max_reconcilable, invoice.name
                )
                allocated_amount = max_reconcilable

            if allocated_amount <= 0:
                continue

            # Create partial reconciliation
            self._create_partial_reconciliation(payment_line, invoice_line, allocated_amount)

            remaining_payment_amount -= allocated_amount

            if remaining_payment_amount <= 0.01:  # Small tolerance for rounding
                break

    def _create_partial_reconciliation(self, payment_line, invoice_line, amount):
        """Create a partial reconciliation between payment line and invoice line"""

        # Determine which line is debit and which is credit
        if payment_line.balance > 0:
            debit_line = payment_line
            credit_line = invoice_line
            debit_amount_currency = amount if payment_line.currency_id else 0
            credit_amount_currency = amount if invoice_line.currency_id else 0
        else:
            debit_line = invoice_line
            credit_line = payment_line
            debit_amount_currency = amount if invoice_line.currency_id else 0
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
                'Created partial reconciliation between payment line %s and invoice line %s for amount %.2f',
                payment_line.id, invoice_line.id, amount
            )
            return partial_reconcile
        except Exception as e:
            _logger.error('Failed to create partial reconciliation: %s', str(e))
            raise UserError(_('Failed to create partial reconciliation: %s') % str(e))


    # ===============================================
    # DEPOSIT FLOW
    # ===============================================

    def action_deposited(self):
        """Open wizard to deposit cheque to bank"""
        # Validate that all selected PDCs are in confirmed state
        non_confirmed_pdcs = self.filtered(lambda p: p.state != 'confirmed')

        if non_confirmed_pdcs:
            raise UserError(_(
                'Only confirmed PDCs can be deposited.\n'
                'Non-confirmed PDCs: %s'
            ) % ', '.join(non_confirmed_pdcs.mapped('name')))

        return {
            'name': _('Cheque Deposit'),
            'type': 'ir.actions.act_window',
            'res_model': 'account.deposit.wizard',
            'view_mode': 'form',
            'view_id': self.env.ref('ns_pdc.view_account_deposit_wizard').id,
            'target': 'new',
            'context': {
                'default_pdc_ids': self.ids,
            }
        }

    # ===============================================
    # HANDOVER FLOW
    # ===============================================

    def action_handover(self):
        """Open wizard to handover cheque to vendor"""
        self.ensure_one()
        if self.state != 'confirmed':
            raise UserError(_('PDC must be in confirmed state to process handover.'))

        return {
            'name': _('PDC Handover'),
            'type': 'ir.actions.act_window',
            'res_model': 'account.pdc.handover.wizard',
            'view_mode': 'form',
            'view_id': self.env.ref('ns_pdc.view_account_pdc_handover_wizard_form').id,
            'target': 'new',
            'context': {
                'default_pdc_id': self.id,
            }
        }

    # ===============================================
    # REALIZATION FLOW
    # ===============================================

    def action_realized(self):
        """
        Realize the PDC - Create journal entry to transfer from cheque-in-hand to bank

        This creates a balancing journal entry that:
        1. Debits Bank Account (increases bank balance)
        2. Credits Cheque-in-Hand Account (decreases cheque-in-hand balance)

        No reconciliation is performed.
        """
        self.ensure_one()
        self._validate_realization()

        # Get all original payments created during confirmation
        original_payments = self.account_payment_ids.filtered(
            lambda p: p.journal_id.cheque_in_hand == True
        )

        if not original_payments:
            raise UserError(_('No cheque-in-hand payment found. Please confirm the PDC first.'))

        # Create transfer journal entry for the total amount
        transfer_move = self._create_transfer_journal_entry(original_payments)

        # Link journal entry to PDC for tracking
        if transfer_move:
            self._link_journal_entries(transfer_move, "PDC Realization Transfer")

        # Update state and realization date
        self.write({
            'state': 'realized',
            'realization_date': fields.Date.context_today(self)
        })

        # Log the realization
        self.message_post(
            body=_('PDC realized successfully\nTransfer Entry: %s\nAmount: %.2f\nFrom: %s\nTo: %s') % (
                transfer_move.name if transfer_move else 'Failed',
                self.amount,
                original_payments[0].journal_id.name if original_payments else 'Unknown',
                self.bank_journal_id.name
            ),
            message_type='notification'
        )

        return transfer_move

    def _validate_realization(self):
        """Centralized validation for PDC realization"""
        # For manual amount PDCs, allocations are not required
        if not self.use_manual_amount and not self.account_pdc_allocation_ids:
            raise UserError(_('No allocations found for this PDC.'))

        if not self.bank_journal_id:
            raise UserError(_('Bank journal is required to realize the PDC.'))

        if self.state != 'deposited':
            raise UserError(_('PDC must be in deposited state before realization.'))

    def _create_transfer_journal_entry(self, original_payments):
        """
        Create journal entry to transfer from cheque-in-hand to bank

        Journal Entry:
        Dr. Bank Account          XXX
            Cr. Cheque-in-Hand        XXX

        No reconciliation performed.
        """
        try:
            # Get journals (use first payment's cheque journal)
            cheque_journal = original_payments[0].journal_id
            bank_journal = self.bank_journal_id

            _logger.info(f"Creating realization entry for PDC {self.name}: From {cheque_journal.name} to {bank_journal.name}")

            # Find the cheque-in-hand account (the liquidity account from cheque journal)
            cheque_account = cheque_journal.default_account_id

            if not cheque_account:
                raise UserError(_('Cheque-in-hand journal "%s" must have a default account configured.') % cheque_journal.name)

            # Find the bank account (the liquidity account from bank journal)
            bank_account = bank_journal.default_account_id

            if not bank_account:
                raise UserError(_('Bank journal "%s" must have a default account configured.') % bank_journal.name)

            # Calculate total amount from all payments
            # total_amount = sum(original_payments.mapped('amount'))
            total_amount = self.amount

            if total_amount <= 0:
                raise UserError(_('Cannot create realization entry with zero or negative amount.'))

            # Get partner (use first payment's partner)
            # partner = original_payments[0].partner_id
            partner = self.partner_id

            # Prepare journal entry lines
            line_vals = []

            # Debit: Bank Account (increase bank balance)
            line_vals.append(Command.create({
                'name': _('PDC Realization - %s - Cheque: %s') % (self.name, self.cheque_number),
                'account_id': bank_account.id,
                'debit': total_amount,
                'credit': 0.0,
                'partner_id': partner.id if partner else False,
            }))

            # Credit: Cheque-in-Hand Account (decrease cheque-in-hand balance)
            line_vals.append(Command.create({
                'name': _('PDC Realization - %s - Cheque: %s') % (self.name, self.cheque_number),
                'account_id': cheque_account.id,
                'debit': 0.0,
                'credit': total_amount,
                'partner_id': partner.id if partner else False,
            }))

            # Prepare journal entry values
            move_vals = {
                'journal_id': bank_journal.id,
                'date': fields.Date.context_today(self),
                'ref': _('PDC Realization - %s - Cheque: %s') % (self.name, self.cheque_number),
                'line_ids': line_vals,
                'move_type': 'entry',  # Explicitly set as journal entry
            }

            # Create and post journal entry
            move = self.env['account.move'].create(move_vals)

            # Validate before posting
            if not move.line_ids:
                raise UserError(_('Failed to create journal entry lines.'))

            # Post the entry
            move.action_post()

            _logger.info(f"Successfully created and posted realization entry {move.name} for PDC {self.name}")

            # Log detailed information
            self.message_post(
                body=_('Realization journal entry created\nEntry: %s\nDr. %s: %.2f\nCr. %s: %.2f') % (
                    move.name,
                    bank_account.name,
                    total_amount,
                    cheque_account.name,
                    total_amount
                ),
                message_type='comment'
            )

            return move

        except Exception as e:
            error_msg = _('Failed to create realization journal entry: %s') % str(e)
            _logger.error(f"Realization entry creation failed for PDC {self.name}: {str(e)}")

            self.message_post(
                body=error_msg,
                message_type='notification'
            )

            raise UserError(error_msg)

    # ===============================================
    # HELPER METHODS
    # ===============================================

    def _get_valid_allocations(self, move_type):
        """Get valid allocations filtered by move type and amount"""
        return self.account_pdc_allocation_ids.filtered(
            lambda a: a.invoice_id
            and a.invoice_id.move_type == move_type
            and a.amount_allocate > 0
        )

    def _get_payment_method_line_for_journal(self, journal, payment_type):
        """
        Get appropriate payment method line for a specific journal

        Args:
            journal: account.journal record
            payment_type: 'inbound' or 'outbound'

        Returns:
            payment_method_line_id (int) or False
        """
        if not journal:
            return False

        # Get the appropriate method lines based on payment type
        method_lines = (journal.inbound_payment_method_line_ids
                       if payment_type == 'inbound'
                       else journal.outbound_payment_method_line_ids)

        # Try to find 'manual' payment method first (most common)
        manual_method = method_lines.filtered(lambda x: x.code == 'manual')
        if manual_method:
            return manual_method[0].id

        # Fallback: return first available method
        if method_lines:
            return method_lines[0].id

        return False

    # ===============================================
    # VIEW ACTIONS
    # ===============================================

    def action_view_payments(self):
        """Smart button action to view all payments related to this PDC (including handover payments)"""
        # Include both regular payments and handover payments
        payment_domain = ['|', ('pdc_id', '=', self.id), ('pdc_handover_id', '=', self.id)]

        return {
            'name': _('Payments'),
            'type': 'ir.actions.act_window',
            'res_model': 'account.payment',
            'view_mode': 'list,form',
            'domain': payment_domain,
            'context': {'default_pdc_id': self.id},
        }

    def action_allocate_invoices(self):
        """Allocate invoices to manual amount PDC payment"""
        self.ensure_one()

        if not self.use_manual_amount:
            raise UserError(_('This action is only available for manual amount PDCs.'))

        if self.state != 'confirmed':
            raise UserError(_('PDC must be confirmed before allocating invoices.'))

        # The wizard will handle finding and validating the payment
        # Just check we have payments created
        if not self.account_payment_ids:
            raise UserError(_('No payments found for this PDC. Please confirm the PDC first.'))

        # Open allocation wizard
        return {
            'name': _('Allocate PDC to Invoices'),
            'type': 'ir.actions.act_window',
            'res_model': 'account.pdc.allocation.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_pdc_id': self.id,
            }
        }

    def action_view_journal_entries(self):
        """Smart button to view all journal entries related to this PDC (using linked entries)"""
        # Use linked journal entries for comprehensive tracking
        all_moves = self.linked_journal_entry_ids

        return {
            'name': _('PDC Journal Entries'),
            'type': 'ir.actions.act_window',
            'res_model': 'account.move',
            'view_mode': 'list,form',
            'domain': [('id', 'in', all_moves.ids)],
            'context': {
                'search_default_posted': 1,
                'default_ref': f'Related to PDC {self.name}',
            }
        }

    def action_test_realization_entry(self):
        """Test method to verify realization journal entry creation (for debugging)"""
        self.ensure_one()

        if self.state != 'deposited':
            raise UserError(_('PDC must be in deposited state to test realization entry.'))

        # Get original payments
        original_payments = self.account_payment_ids.filtered(
            lambda p: p.journal_id.cheque_in_hand == True
        )

        if not original_payments:
            raise UserError(_('No cheque-in-hand payment found.'))

        # Test the journal entry creation without changing state
        test_move = self._create_transfer_journal_entry(original_payments)

        if test_move:
            return {
                'name': _('Test Realization Entry'),
                'type': 'ir.actions.act_window',
                'res_model': 'account.move',
                'view_mode': 'form',
                'res_id': test_move.id,
                'target': 'current',
            }
        else:
            raise UserError(_('Failed to create test realization entry.'))

    @api.depends('linked_journal_entry_ids')
    def _compute_journal_entry_count(self):
        for record in self:
            # Use linked journal entries for accurate count
            record.journal_entry_count = len(record.linked_journal_entry_ids)

    @api.depends('use_manual_amount', 'state', 'account_payment_ids', 'account_payment_ids.state', 'account_payment_ids.move_id.line_ids.reconciled', 'account_payment_ids.move_id.line_ids.amount_residual')
    def _compute_has_unallocated_amount(self):
        for record in self:
            if not record.use_manual_amount or record.state != 'confirmed':
                record.has_unallocated_amount = False
                continue

            # Check if there's an unallocated payment
            # A payment is unallocated if it has unreconciled move lines
            has_unallocated = False
            for payment in record.account_payment_ids:
                if payment.state in ('in_process', 'paid') and payment.move_id:
                    # Check if payment has unreconciled receivable/payable lines
                    payment_lines = payment.move_id.line_ids.filtered(
                        lambda l: l.account_id.account_type in ('asset_receivable', 'liability_payable')
                        and not l.reconciled
                        and abs(l.amount_residual) > 0.01
                    )
                    if payment_lines:
                        has_unallocated = True
                        break

            _logger.info(f"PDC {record.name}: use_manual_amount={record.use_manual_amount}, state={record.state}, payments={len(record.account_payment_ids)}, has_unallocated={has_unallocated}")
            record.has_unallocated_amount = has_unallocated

    # ===============================================
    # STATE CHANGES
    # ===============================================

    def action_cancel(self):
        """Cancel the PDC"""
        self.write({'state': 'canceled'})
        return True

    def action_return(self):
        """Open return wizard to get return date and reason"""
        return {
            'name': _('PDC Return'),
            'type': 'ir.actions.act_window',
            'res_model': 'account.pdc.return.wizard',
            'view_mode': 'form',
            'view_id': self.env.ref('ns_pdc.view_account_pdc_return_wizard').id,
            'target': 'new',
            'context': {
                'default_pdc_id': self.id,
            }
        }

    def process_return(self, return_date, return_reason=None):
        """
        Enhanced PDC return handling for both scenarios with specified return date:

        Scenario 1 - Non-handover (confirmed/deposited):
        1. Create bank entries with return date
        2. Reverse original payments with proper unreconciliation
        3. Create matching entries that reconcile with originals

        Scenario 2 - Handover:
        1. Reverse handover payments (unreconcile bills)
        2. Reverse original customer payments (unreconcile invoices)
        3. Create matching reversal entries that reconcile with originals
        4. Keep handover breakdown records for audit
        """
        self.ensure_one()

        # Store return date in context for journal entries
        self = self.with_context(return_date=return_date, return_reason=return_reason)

        # Add comprehensive logging
        self.message_post(
            body=_('Return process started for PDC %s in state: %s on date: %s') % (self.name, self.state, return_date),
            message_type='notification'
        )

        try:
            if self.state == 'handover':
                result = self._handle_handover_return()
                self.message_post(
                    body=_('Handover return process completed. Created %d journal entries.') % len(result),
                    message_type='notification'
                )
                return result
            else:
                result = self._handle_non_handover_return()
                self.message_post(
                    body=_('Non-handover return process completed. Created %d journal entries.') % len(result),
                    message_type='notification'
                )
                return result
        except Exception as e:
            error_msg = _('Return process failed: %s') % str(e)
            self.message_post(
                body=error_msg,
                message_type='notification'
            )
            raise UserError(error_msg)

    def _handle_non_handover_return(self):
        """Handle return for confirmed or deposited PDCs"""

        # Validate state
        if self.state not in ('confirmed', 'deposited'):
            raise UserError(_('PDC must be in confirmed or deposited state to process non-handover return.'))

        self.message_post(
            body=_('Processing non-handover return for PDC in %s state') % self.state,
            message_type='notification'
        )

        reversed_moves = []

        # Step 1: Create bank entries for deposited cheques (both entries)
        if self.state == 'deposited':
            self.message_post(
                body=_('Creating bank entries for deposited cheque return'),
                message_type='notification'
            )
            bank_entries = self._create_return_bank_entry()
            reversed_moves.extend(bank_entries)
            self.message_post(
                body=_('Bank entries created: %s') % ', '.join([entry.name for entry in bank_entries]),
                message_type='notification'
            )

        # Step 2: Handle payment reversals with proper unreconciliation
        original_payments = self.account_payment_ids.filtered(lambda p: p.state in ('in_process', 'paid'))
        self.message_post(
            body=_('Found %d original payments to reverse: %s') % (
                len(original_payments),
                ', '.join(original_payments.mapped('name'))
            ),
            message_type='notification'
        )

        if original_payments:
            payment_reversals = self._reverse_payments_with_unreconciliation(original_payments)
            reversed_moves.extend(payment_reversals)
            self.message_post(
                body=_('Created %d payment reversal entries') % len(payment_reversals),
                message_type='notification'
            )
        else:
            self.message_post(
                body=_('No posted payments found to reverse'),
                message_type='notification'
            )

        # Update PDC state and block customer
        self.write({'state': 'return'})

        # Block customer for future PDC transactions
        self.partner_id.block_customer_pdc(
            self.partner_id.id,
            f'PDC {self.name} returned - Cheque number: {self.cheque_number}'
        )
        self.message_post(
            body=_('PDC state updated to return. Total reversal entries created: %d') % len(reversed_moves),
            message_type='notification'
        )

        return [move.id for move in reversed_moves]

    def _handle_handover_return(self):
        """Handle return for handover PDCs"""

        self.message_post(
            body=_('Processing handover return for PDC'),
            message_type='notification'
        )

        reversed_moves = []

        # Step 1: Reverse handover payments (unreconcile bills)
        handover_payments = self.env['account.payment'].search([
            ('pdc_handover_id', '=', self.id),
            ('state', 'in', ('in_process', 'paid'))
        ])

        self.message_post(
            body=_('Found %d handover payments to reverse: %s') % (
                len(handover_payments),
                ', '.join(handover_payments.mapped('name'))
            ),
            message_type='notification'
        )

        if handover_payments:
            handover_reversals = self._reverse_payments_with_unreconciliation(handover_payments)
            reversed_moves.extend(handover_reversals)
            self.message_post(
                body=_('Created %d handover reversal entries') % len(handover_reversals),
                message_type='notification'
            )

        # Step 2: Reverse original customer payments (unreconcile invoices)
        original_payments = self.account_payment_ids.filtered(lambda p: p.state in ('in_process', 'paid'))
        self.message_post(
            body=_('Found %d original payments to reverse: %s') % (
                len(original_payments),
                ', '.join(original_payments.mapped('name'))
            ),
            message_type='notification'
        )

        if original_payments:
            payment_reversals = self._reverse_payments_with_unreconciliation(original_payments)
            reversed_moves.extend(payment_reversals)
            self.message_post(
                body=_('Created %d original payment reversal entries') % len(payment_reversals),
                message_type='notification'
            )

        # Update PDC state (keep handover breakdown for audit) and block customer
        self.write({'state': 'return'})

        # Block customer for future PDC transactions
        self.partner_id.block_customer_pdc(
            self.partner_id.id,
            f'Handover PDC {self.name} returned - Cheque number: {self.cheque_number}'
        )

        self.message_post(
            body=_('Handover PDC state updated to return. Total reversal entries created: %d') % len(reversed_moves),
            message_type='notification'
        )

        return [move.id for move in reversed_moves]

    def _create_return_bank_entry(self):
        """Create BOTH bank entries for deposited cheque return"""

        if not self.bank_journal_id:
            raise UserError(_('Bank journal is required for deposited cheque return.'))

        # Get cheque-in-hand journal
        cheque_journal = self.env['account.journal'].search([
            ('cheque_in_hand', '=', True)
        ], limit=1)

        if not cheque_journal:
            raise UserError(_('Cheque-in-hand journal not found.'))

        # Get accounts
        bank_account = self.bank_journal_id.default_account_id
        cheque_account = cheque_journal.default_account_id

        if not bank_account or not cheque_account:
            raise UserError(_('Journal accounts not properly configured.'))

        # Get return date from context
        return_date = self.env.context.get('return_date', fields.Date.context_today(self))

        created_moves = []

        # FIRST ENTRY: Cheque returned from bank
        # Dr. Cheque-in-Hand 1,000 | Cr. Bank 1,000
        line_vals_1 = []
        line_vals_1.append(Command.create({
            'name': _('Return Cheque - %s') % self.cheque_number,
            'account_id': cheque_account.id,
            'debit': self.amount,
            'credit': 0.0,
            'partner_id': self.partner_id.id,
        }))
        line_vals_1.append(Command.create({
            'name': _('Return Cheque - %s') % self.cheque_number,
            'account_id': bank_account.id,
            'debit': 0.0,
            'credit': self.amount,
            'partner_id': self.partner_id.id,
        }))

        move_vals_1 = {
            'journal_id': self.bank_journal_id.id,
            'date': return_date,
            'ref': _('Return Cheque - %s') % self.cheque_number,
            'line_ids': line_vals_1,
        }

        move_1 = self.env['account.move'].create(move_vals_1)
        move_1.action_post()
        created_moves.append(move_1)
        self._link_journal_entries(move_1, "Return Bank Entry - Cheque Back from Bank")

        # SECOND ENTRY: Original deposit entry (that should have been created on deposit date)
        # Dr. Bank 1,000 | Cr. Cheque-in-Hand 1,000
        line_vals_2 = []
        line_vals_2.append(Command.create({
            'name': _('Deposit Entry (Posted on Return) - %s') % self.cheque_number,
            'account_id': bank_account.id,
            'debit': self.amount,
            'credit': 0.0,
            'partner_id': self.partner_id.id,
        }))
        line_vals_2.append(Command.create({
            'name': _('Deposit Entry (Posted on Return) - %s') % self.cheque_number,
            'account_id': cheque_account.id,
            'debit': 0.0,
            'credit': self.amount,
            'partner_id': self.partner_id.id,
        }))

        move_vals_2 = {
            'journal_id': self.bank_journal_id.id,
            'date': return_date,  # Posted on return date but represents deposit
            'ref': _('Deposit Entry (Posted on Return) - %s') % self.cheque_number,
            'line_ids': line_vals_2,
        }

        move_2 = self.env['account.move'].create(move_vals_2)
        move_2.action_post()
        created_moves.append(move_2)
        self._link_journal_entries(move_2, "Return Bank Entry - Original Deposit Entry")

        return created_moves

    def _reverse_payments_with_unreconciliation(self, payments):
        """Reverse payments and handle proper unreconciliation"""

        reversed_moves = []

        for payment in payments:
            self.message_post(
                body=_('Processing reversal for payment: %s (Amount: %.2f)') % (payment.name, payment.amount),
                message_type='notification'
            )

            # Step 1: Unreconcile all partial reconciliations
            unreconciled_count = self._unreconcile_payment(payment)
            self.message_post(
                body=_('Unreconciled %d partial reconciliations for payment %s') % (unreconciled_count, payment.name),
                message_type='notification'
            )

            # Step 2: Create reversal entry
            reversal_move = self._create_payment_reversal(payment)
            reversed_moves.append(reversal_move)
            self.message_post(
                body=_('Created reversal entry: %s for payment %s') % (reversal_move.name, payment.name),
                message_type='notification'
            )

            # Step 3: Reconcile original with reversal
            reconciled = self._reconcile_payment_with_reversal(payment, reversal_move)
            self.message_post(
                body=_('Reconciled original payment with reversal: %s (Success: %s)') % (payment.name, reconciled),
                message_type='notification'
            )

        return reversed_moves

    def _unreconcile_payment(self, payment):
        """Unreconcile all partial reconciliations for a payment"""

        # Get payment's receivable/payable lines
        payment_lines = payment.move_id.line_ids.filtered(
            lambda l: l.account_id.account_type in ('asset_receivable', 'liability_payable')
        )

        total_unreconciled = 0
        for line in payment_lines:
            # Find and remove all partial reconciliations
            partial_reconciles = self.env['account.partial.reconcile'].search([
                '|',
                ('debit_move_id', '=', line.id),
                ('credit_move_id', '=', line.id)
            ])

            if partial_reconciles:
                total_unreconciled += len(partial_reconciles)
                partial_reconciles.unlink()

        return total_unreconciled

    def _create_payment_reversal(self, payment):
        """Create exact reversal of payment journal entry"""

        # Get original move lines
        original_lines = payment.move_id.line_ids

        # Create reversal lines (flip debit/credit)
        line_vals = []
        for line in original_lines:
            line_vals.append(Command.create({
                'name': _('Return Cheque Reversal - %s') % self.cheque_number,
                'account_id': line.account_id.id,
                'debit': line.credit,  # Flip amounts
                'credit': line.debit,  # Flip amounts
                'partner_id': line.partner_id.id if line.partner_id else False,
            }))

        # Get return date from context
        return_date = self.env.context.get('return_date', fields.Date.context_today(self))

        # Create reversal move
        reversal_vals = {
            'journal_id': payment.journal_id.id,
            'date': return_date,
            'ref': _('Return Cheque Reversal - %s') % self.cheque_number,
            'line_ids': line_vals,
        }

        reversal_move = self.env['account.move'].create(reversal_vals)
        reversal_move.action_post()

        # Link reversal entry to PDC for tracking
        self._link_journal_entries(reversal_move, "Return Payment Reversal")

        return reversal_move

    def _reconcile_payment_with_reversal(self, payment, reversal_move):
        """Reconcile original payment with its reversal"""

        # Get receivable/payable lines from both moves
        payment_lines = payment.move_id.line_ids.filtered(
            lambda l: l.account_id.account_type in ('asset_receivable', 'liability_payable')
        )

        reversal_lines = reversal_move.line_ids.filtered(
            lambda l: l.account_id.account_type in ('asset_receivable', 'liability_payable')
        )

        reconciled_count = 0
        # Match and reconcile lines with same account
        for payment_line in payment_lines:
            matching_reversal_line = reversal_lines.filtered(
                lambda l: l.account_id.id == payment_line.account_id.id
            )

            if matching_reversal_line:
                try:
                    # Create full reconciliation
                    lines_to_reconcile = payment_line | matching_reversal_line[:1]  # Take first match
                    if lines_to_reconcile and len(lines_to_reconcile) == 2:
                        lines_to_reconcile.reconcile()
                        reconciled_count += 1
                except Exception as e:
                    self.message_post(
                        body=_('Failed to reconcile lines: %s') % str(e),
                        message_type='notification'
                    )

        return reconciled_count > 0

    # ===============================================
    # RESET TO DRAFT FUNCTIONALITY
    # ===============================================

    def action_reset_to_draft(self):
        """Open wizard to reset PDC to draft state with user confirmation"""
        self.ensure_one()

        # Validate that reset is allowed
        if self.state == 'draft':
            raise UserError(_('PDC is already in draft state.'))

        if self.state == 'canceled':
            raise UserError(_('Cannot reset a cancelled PDC. Please create a new one.'))

        return {
            'name': _('Reset PDC to Draft'),
            'type': 'ir.actions.act_window',
            'res_model': 'account.pdc.reset.wizard',
            'view_mode': 'form',
            'view_id': self.env.ref('ns_pdc.view_account_pdc_reset_wizard_form').id,
            'target': 'new',
            'context': {
                'default_pdc_id': self.id,
            }
        }

    def action_bulk_handover(self):
        """Open wizard for bulk handover of selected PDCs"""
        # Get selected records from context
        selected_ids = self.env.context.get('active_ids', [])

        if not selected_ids:
            raise UserError(_('Please select at least one PDC record for bulk handover.'))

        # Validate that all selected PDCs are in confirmed state
        selected_pdcs = self.browse(selected_ids)
        non_confirmed_pdcs = selected_pdcs.filtered(lambda p: p.state != 'confirmed')

        if non_confirmed_pdcs:
            raise UserError(_(
                'Only confirmed PDCs can be handed over.\n'
                'Non-confirmed PDCs: %s'
            ) % ', '.join(non_confirmed_pdcs.mapped('name')))

        return {
            'name': _('Bulk PDC Handover'),
            'type': 'ir.actions.act_window',
            'res_model': 'account.pdc.bulk.handover.wizard',
            'view_mode': 'form',
            'view_id': self.env.ref('ns_pdc.view_account_pdc_bulk_handover_wizard_form').id,
            'target': 'new',
            'context': {
                'active_model': 'account.pdc',
                'active_ids': selected_ids,
            }
        }