from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
import logging

_logger = logging.getLogger(__name__)


class AccountPDCBulkHandoverWizard(models.TransientModel):
    _name = 'account.pdc.bulk.handover.wizard'
    _description = 'PDC Bulk Handover Wizard'

    pdc_ids = fields.Many2many('account.pdc', string='PDC Records', required=True, readonly=True)
    handover_to_partner_id = fields.Many2one('res.partner', string='Handover To', required=True,
                                           help="The vendor who will receive these cash cheques")
    handover_date = fields.Date(string='Handover Date', default=fields.Date.today, required=True)
    notes = fields.Text(string='Notes')

    # Summary fields
    pdc_count = fields.Integer(string='PDC Count', compute='_compute_summary', store=True)
    total_amount = fields.Float(string='Total Amount', compute='_compute_summary', store=True)
    pdc_line_ids = fields.One2many('account.pdc.bulk.handover.line', 'wizard_id',
                                  string='PDC Details', compute='_compute_pdc_lines', store=True)

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        context = self.env.context

        # Get selected PDC records from context
        if context.get('active_model') == 'account.pdc' and context.get('active_ids'):
            pdc_ids = context['active_ids']
            res['pdc_ids'] = [(6, 0, pdc_ids)]

        return res

    @api.depends('pdc_ids')
    def _compute_summary(self):
        for record in self:
            record.pdc_count = len(record.pdc_ids)
            record.total_amount = sum(record.pdc_ids.mapped('amount'))

    @api.depends('pdc_ids')
    def _compute_pdc_lines(self):
        for record in self:
            lines = []
            for pdc in record.pdc_ids:
                lines.append((0, 0, {
                    'pdc_id': pdc.id,
                    'partner_id': pdc.partner_id.id,
                    'amount': pdc.amount,
                    'cheque_number': pdc.cheque_number,
                    'cheque_date': pdc.cheque_date,
                    'current_state': pdc.state,
                }))
            record.pdc_line_ids = lines

    @api.constrains('pdc_ids')
    def _check_pdc_selection(self):
        for record in self:
            if not record.pdc_ids:
                raise ValidationError(_('Please select at least one PDC record.'))

    def action_confirm(self):
        """Process the bulk handover"""
        self.ensure_one()
        self._validate_bulk_handover()

        # Process handover for each PDC
        processed_pdcs = []
        created_payments = []
        errors = []

        for pdc in self.pdc_ids:
            try:
                # Create simple handover payment for each PDC
                payment = self._create_pdc_handover_payment(pdc)
                created_payments.append(payment)

                # Update PDC with handover information
                pdc.write({
                    'state': 'handover',
                    'handover_date': self.handover_date,
                    'handover_to_partner_id': self.handover_to_partner_id.id,
                    'handover_notes': self.notes,
                })

                # Log the handover
                pdc.message_post(
                    body=_('PDC handed over via bulk handover\nHandover To: %s\nAmount: %.2f\nNotes: %s') % (
                        self.handover_to_partner_id.name,
                        pdc.amount,
                        self.notes or 'None'
                    ),
                    message_type='notification'
                )

                processed_pdcs.append(pdc)
                _logger.info(f"Successfully processed bulk handover for PDC {pdc.name}")

            except Exception as e:
                error_msg = _('Failed to process PDC %s: %s') % (pdc.name, str(e))
                errors.append(error_msg)
                _logger.error(f"Bulk handover error for PDC {pdc.name}: {str(e)}")

        # Show results
        return self._show_bulk_handover_results(processed_pdcs, created_payments, errors)

    def _validate_bulk_handover(self):
        """Validate bulk handover data"""
        # Check all PDCs are in confirmed state
        non_confirmed_pdcs = self.pdc_ids.filtered(lambda p: p.state != 'confirmed')
        if non_confirmed_pdcs:
            raise UserError(_(
                'All PDCs must be in confirmed state for bulk handover.\n'
                'Non-confirmed PDCs: %s'
            ) % ', '.join(non_confirmed_pdcs.mapped('name')))

        # Check for blocked customers
        blocked_partners = self.pdc_ids.mapped('partner_id').filtered('pdc_blocked')
        if blocked_partners:
            raise UserError(_(
                'The following customers are blocked for PDC transactions:\n%s\n\n'
                'Please contact your administrator to unblock these customers.'
            ) % '\n'.join([
                f'- {partner.name} (Blocked on: {partner.pdc_block_date}, Reason: {partner.pdc_block_reason})'
                for partner in blocked_partners
            ]))

        # Validate amounts
        zero_amount_pdcs = self.pdc_ids.filtered(lambda p: p.amount <= 0)
        if zero_amount_pdcs:
            raise UserError(_(
                'PDCs with zero or negative amounts cannot be handed over:\n%s'
            ) % ', '.join(zero_amount_pdcs.mapped('name')))

    def _create_pdc_handover_payment(self, pdc):
        """Create simple handover payment for a specific PDC (same logic as individual handover)"""
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
            'amount': pdc.amount,
            'date': self.handover_date,
            'journal_id': cheque_journal.id,
            'payment_method_line_id': payment_method_line_id,
            'memo': _('Bulk PDC Handover - %s - Cheque: %s') % (pdc.name, pdc.cheque_number),
            'pdc_handover_id': pdc.id,
            'is_handover_payment': True,
        }

        # Create and post payment
        payment = self.env['account.payment'].create(payment_vals)
        payment.action_post()

        # Link handover payment journal entry to PDC for tracking
        if payment.move_id:
            pdc._link_journal_entries(payment.move_id, "Bulk Handover Payment")

        _logger.info(f"Created bulk handover payment {payment.name} for PDC {pdc.name}")

        return payment

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

    def _show_bulk_handover_results(self, processed_pdcs, created_payments, errors):
        """Show results of bulk handover operation"""
        success_count = len(processed_pdcs)
        error_count = len(errors)

        # Create result message
        if success_count > 0 and error_count == 0:
            # All successful
            message = _('Bulk handover completed successfully!\n\n'
                       'Processed %d PDCs\n'
                       'Created %d payments\n'
                       'Handover Partner: %s') % (
                success_count, len(created_payments), self.handover_to_partner_id.name
            )
            notification_type = 'success'
        elif success_count > 0 and error_count > 0:
            # Partial success
            message = _('Bulk handover completed with some errors.\n\n'
                       'Successfully processed: %d PDCs\n'
                       'Failed: %d PDCs\n\n'
                       'Errors:\n%s') % (
                success_count, error_count, '\n'.join(errors)
            )
            notification_type = 'warning'
        else:
            # All failed
            message = _('Bulk handover failed for all PDCs.\n\n'
                       'Errors:\n%s') % '\n'.join(errors)
            notification_type = 'danger'

        # Show notification
        notification = {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Bulk Handover Results'),
                'message': message,
                'type': notification_type,
                'sticky': True,
            }
        }

        # If we have successful payments, also show them
        if created_payments:
            # Show payments in list view
            return {
                'name': _('Bulk Handover Payments'),
                'type': 'ir.actions.act_window',
                'res_model': 'account.payment',
                'view_mode': 'list,form',
                'domain': [('id', 'in', [p.id for p in created_payments])],
                'context': {
                    'search_default_posted': 1,
                }
            }

        return notification


class AccountPDCBulkHandoverLine(models.TransientModel):
    _name = 'account.pdc.bulk.handover.line'
    _description = 'PDC Bulk Handover Line'

    wizard_id = fields.Many2one('account.pdc.bulk.handover.wizard', required=True, ondelete='cascade')
    pdc_id = fields.Many2one('account.pdc', string='PDC', required=True, readonly=True)
    partner_id = fields.Many2one('res.partner', string='Customer', readonly=True)
    amount = fields.Float(string='Amount', readonly=True)
    cheque_number = fields.Char(string='Cheque Number', readonly=True)
    cheque_date = fields.Date(string='Cheque Date', readonly=True)
    current_state = fields.Selection(related='pdc_id.state', string='State', readonly=True)