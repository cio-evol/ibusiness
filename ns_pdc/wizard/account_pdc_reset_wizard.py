from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
import logging

_logger = logging.getLogger(__name__)


class AccountPDCResetWizard(models.TransientModel):
    _name = 'account.pdc.reset.wizard'
    _description = 'PDC Reset to Draft Wizard'

    pdc_id = fields.Many2one('account.pdc', string='PDC Record', required=True)
    pdc_name = fields.Char(related='pdc_id.name', string='PDC Name', readonly=True)
    current_state = fields.Selection(related='pdc_id.state', string='Current State', readonly=True)
    partner_id = fields.Many2one(related='pdc_id.partner_id', string='Partner', readonly=True)
    amount = fields.Float(related='pdc_id.amount', string='Amount', readonly=True)

    # Information fields to show what will be affected
    allocation_count = fields.Integer(string='Allocations to Cancel', compute='_compute_affected_records')
    handover_breakdown_count = fields.Integer(string='Handover Breakdowns to Cancel', compute='_compute_affected_records')
    payment_count = fields.Integer(string='Payments to Review', compute='_compute_affected_records')
    journal_entry_count = fields.Integer(string='Journal Entries Linked', compute='_compute_affected_records')

    # Warning messages
    warning_message = fields.Text(string='Warning', compute='_compute_warning_message')

    # Confirmation
    confirm_reset = fields.Boolean(string='I confirm that I want to reset this PDC to draft', default=False)
    reset_reason = fields.Text(string='Reason for Reset', required=True,
                              help="Please provide a reason for resetting this PDC to draft state")

    @api.depends('pdc_id')
    def _compute_affected_records(self):
        for record in self:
            if record.pdc_id:
                record.allocation_count = len(record.pdc_id.account_pdc_allocation_ids)
                record.handover_breakdown_count = len(record.pdc_id.handover_breakdown_ids)
                record.payment_count = len(record.pdc_id.account_payment_ids)
                record.journal_entry_count = len(record.pdc_id.linked_journal_entry_ids)
            else:
                record.allocation_count = 0
                record.handover_breakdown_count = 0
                record.payment_count = 0
                record.journal_entry_count = 0

    @api.depends('pdc_id', 'allocation_count', 'handover_breakdown_count', 'payment_count', 'current_state')
    def _compute_warning_message(self):
        for record in self:
            if not record.pdc_id:
                record.warning_message = ""
                continue

            warnings = []

            # State-specific warnings
            if record.current_state == 'realized':
                warnings.append("⚠️ This PDC is REALIZED. Resetting will affect bank reconciliations.")
            elif record.current_state == 'deposited':
                warnings.append("⚠️ This PDC is DEPOSITED. Bank entries may need manual correction.")
            elif record.current_state == 'handover':
                warnings.append("⚠️ This PDC is HANDED OVER. Vendor payments will be affected.")

            # Allocation warnings
            if record.allocation_count > 0:
                warnings.append(f"• {record.allocation_count} invoice allocation(s) will be cancelled")

            if record.handover_breakdown_count > 0:
                warnings.append(f"• {record.handover_breakdown_count} handover breakdown(s) will be cancelled")

            if record.payment_count > 0:
                warnings.append(f"• {record.payment_count} payment(s) will be CANCELLED")

            if record.journal_entry_count > 0:
                warnings.append(f"• {record.journal_entry_count} journal entries are linked (manual review required)")

            # Customer blocking warning
            if record.pdc_id.partner_id.pdc_blocked:
                warnings.append(f"⚠️ Customer {record.pdc_id.partner_id.name} is currently blocked for PDC transactions")

            if warnings:
                record.warning_message = "IMPACT ANALYSIS:\n" + "\n".join(warnings) + "\n\nPlease ensure you understand these implications before proceeding."
            else:
                record.warning_message = "No major impacts identified. Safe to reset to draft."

    @api.constrains('confirm_reset')
    def _check_confirmation(self):
        for record in self:
            if not record.confirm_reset:
                raise ValidationError(_("Please confirm that you want to reset this PDC to draft state."))

    def action_reset_to_draft(self):
        """Execute the reset to draft operation"""
        self.ensure_one()

        if not self.confirm_reset:
            raise UserError(_("Please confirm that you want to reset this PDC to draft state."))

        if not self.reset_reason:
            raise UserError(_("Please provide a reason for resetting this PDC to draft state."))

        pdc = self.pdc_id

        # Validate current state allows reset
        if pdc.state == 'draft':
            raise UserError(_("PDC is already in draft state."))

        if pdc.state == 'canceled':
            raise UserError(_("Cannot reset a cancelled PDC. Please create a new one."))

        _logger.info(f"Starting reset to draft process for PDC {pdc.name} from state {pdc.state}")

        try:
            # Step 1: Log the reset action
            pdc.message_post(
                body=_('PDC Reset to Draft initiated by %s\nReason: %s\nOriginal State: %s') % (
                    self.env.user.name,
                    self.reset_reason,
                    dict(pdc._fields['state'].selection).get(pdc.state)
                ),
                message_type='notification'
            )

            # Step 2: Cancel allocations
            self._cancel_allocations(pdc)

            # Step 3: Cancel handover breakdowns
            self._cancel_handover_breakdowns(pdc)

            # Step 4: Handle payments and reconciliations
            self._handle_payments_reset(pdc)

            # Step 5: Cancel realization entries if PDC is realized
            self._handle_realization_entries_reset(pdc)

            # Step 6: Clear PDC fields
            self._clear_pdc_fields(pdc)

            # Step 7: Set state to draft
            pdc.write({'state': 'draft'})

            _logger.info(f"Successfully reset PDC {pdc.name} to draft state")

            # Step 8: Final success message
            pdc.message_post(
                body=_('PDC successfully reset to draft state\nReason: %s\nAll allocations and handover breakdowns have been cancelled.') % self.reset_reason,
                message_type='notification'
            )

            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Success'),
                    'message': _('PDC %s has been successfully reset to draft state.') % pdc.name,
                    'type': 'success',
                    'sticky': False,
                    'next': {'type': 'ir.actions.act_window_close'},
                }
            }

        except Exception as e:
            error_msg = _('Failed to reset PDC to draft: %s') % str(e)
            pdc.message_post(
                body=error_msg,
                message_type='notification'
            )
            _logger.error(f"Reset to draft failed for PDC {pdc.name}: {str(e)}")
            raise UserError(error_msg)

    def _cancel_allocations(self, pdc):
        """Cancel all PDC allocations"""
        allocations = pdc.account_pdc_allocation_ids
        if allocations:
            _logger.info(f"Cancelling {len(allocations)} allocations for PDC {pdc.name}")

            # Log each allocation being cancelled
            for allocation in allocations:
                pdc.message_post(
                    body=_('Cancelled allocation: Invoice %s, Amount: %.2f') % (
                        allocation.invoice_id.name,
                        allocation.amount_allocate
                    ),
                    message_type='comment'
                )

            # Delete allocations
            allocations.unlink()

            pdc.message_post(
                body=_('All %d invoice allocations have been cancelled') % len(allocations),
                message_type='notification'
            )

    def _cancel_handover_breakdowns(self, pdc):
        """Cancel all handover breakdowns"""
        handover_breakdowns = pdc.handover_breakdown_ids
        if handover_breakdowns:
            _logger.info(f"Cancelling {len(handover_breakdowns)} handover breakdowns for PDC {pdc.name}")

            # Log each breakdown being cancelled
            for breakdown in handover_breakdowns:
                pdc.message_post(
                    body=_('Cancelled handover breakdown: Bill %s, Amount: %.2f') % (
                        breakdown.bill_id.name,
                        breakdown.amount_allocate
                    ),
                    message_type='comment'
                )

            # Delete handover breakdowns
            handover_breakdowns.unlink()

            pdc.message_post(
                body=_('All %d handover breakdowns have been cancelled') % len(handover_breakdowns),
                message_type='notification'
            )

    def _handle_payments_reset(self, pdc):
        """Handle payments during reset - cancel/reverse all related payments"""
        # Get regular payments linked to PDC
        regular_payments = pdc.account_payment_ids

        # Get handover payments linked to PDC
        handover_payments = self.env['account.payment'].search([('pdc_handover_id', '=', pdc.id)])

        all_payments = regular_payments | handover_payments

        if all_payments:
            _logger.info(f"Found {len(all_payments)} payments to cancel for PDC {pdc.name}")

            # Cancel each payment with proper logging
            for payment in all_payments:
                payment_type = "Handover" if payment.pdc_handover_id else "Regular"

                try:
                    # Log the cancellation reason in the payment
                    payment.message_post(
                        body=_('Payment cancelled due to PDC reset to draft\nPDC: %s\nReset Reason: %s\nReset by: %s\nReset Date: %s') % (
                            pdc.name,
                            self.reset_reason,
                            self.env.user.name,
                            fields.Date.context_today(self)
                        ),
                        message_type='notification'
                    )

                    # Cancel the payment based on its state
                    if payment.state == 'draft':
                        # If draft, just delete it
                        payment.unlink()
                        pdc.message_post(
                            body=_('Deleted draft payment (%s): %s (Amount: %.2f)') % (payment_type, payment.name, payment.amount),
                            message_type='notification'
                        )
                    elif payment.state in ('in_process', 'paid'):
                        # If in_process/paid, cancel it properly
                        payment.action_cancel()
                        pdc.message_post(
                            body=_('Cancelled posted payment (%s): %s (Amount: %.2f)') % (payment_type, payment.name, payment.amount),
                            message_type='notification'
                        )
                    elif payment.state == 'canceled':
                        # Already canceled, just log
                        pdc.message_post(
                            body=_('Payment already cancelled (%s): %s (Amount: %.2f)') % (payment_type, payment.name, payment.amount),
                            message_type='comment'
                        )
                    else:
                        # For other states, try to cancel
                        try:
                            payment.action_cancel()
                            pdc.message_post(
                                body=_('Cancelled payment (%s): %s (Amount: %.2f, State was: %s)') % (payment_type, payment.name, payment.amount, payment.state),
                                message_type='notification'
                            )
                        except Exception as e:
                            # If can't cancel, log the issue
                            pdc.message_post(
                                body=_('⚠️ Could not cancel payment (%s): %s (Amount: %.2f, State: %s) - Error: %s') % (
                                    payment_type, payment.name, payment.amount, payment.state, str(e)
                                ),
                                message_type='notification'
                            )

                except Exception as e:
                    error_msg = _('Error processing payment %s: %s') % (payment.name, str(e))
                    _logger.error(f"Payment cancellation error for PDC {pdc.name}: {error_msg}")
                    pdc.message_post(
                        body=_('⚠️ Error cancelling payment (%s): %s - %s') % (payment_type, payment.name, str(e)),
                        message_type='notification'
                    )

            pdc.message_post(
                body=_('Processed %d payment(s) for cancellation during PDC reset') % len(all_payments),
                message_type='notification'
            )

    def _handle_realization_entries_reset(self, pdc):
        """Cancel realization entries for realized PDCs"""
        if pdc.state != 'realized':
            return

        # Find realization entries from linked journal entries
        realization_entries = pdc.linked_journal_entry_ids.filtered(
            lambda move: 'PDC Realization' in (move.ref or '') and move.state == 'posted'
        )

        if realization_entries:
            _logger.info(f"Found {len(realization_entries)} realization entries to cancel for PDC {pdc.name}")

            for entry in realization_entries:
                try:
                    # Log the cancellation reason in the journal entry
                    entry.message_post(
                        body=_('Journal entry cancelled due to PDC reset to draft\nPDC: %s\nReset Reason: %s\nReset by: %s\nReset Date: %s') % (
                            pdc.name,
                            self.reset_reason,
                            self.env.user.name,
                            fields.Date.context_today(self)
                        ),
                        message_type='notification'
                    )

                    # Cancel the journal entry
                    entry.button_draft()
                    entry.button_cancel()

                    pdc.message_post(
                        body=_('Cancelled realization journal entry: %s (Amount: %.2f)') % (entry.name, abs(sum(entry.line_ids.mapped('debit')))),
                        message_type='notification'
                    )

                except Exception as e:
                    error_msg = _('Error cancelling realization entry %s: %s') % (entry.name, str(e))
                    _logger.error(f"Realization entry cancellation error for PDC {pdc.name}: {error_msg}")
                    pdc.message_post(
                        body=_('⚠️ Could not cancel realization entry: %s - Error: %s') % (entry.name, str(e)),
                        message_type='notification'
                    )

            pdc.message_post(
                body=_('Processed %d realization journal entries for cancellation') % len(realization_entries),
                message_type='notification'
            )
        else:
            pdc.message_post(
                body=_('No realization journal entries found to cancel'),
                message_type='comment'
            )

    def _clear_pdc_fields(self, pdc):
        """Clear PDC specific fields that should be reset"""
        fields_to_clear = {
            'deposit_date': False,
            'realization_date': False,
            'handover_date': False,
            'handover_to_partner_id': False,
            'handover_notes': False,
            'handover_payment_id': False,
        }

        pdc.write(fields_to_clear)

        _logger.info(f"Cleared process-specific fields for PDC {pdc.name}")
        pdc.message_post(
            body=_('Process-specific fields (deposit date, realization date, handover info) have been cleared'),
            message_type='comment'
        )

    def action_cancel(self):
        """Cancel the wizard without making changes"""
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Cancelled'),
                'message': _('Reset to draft operation was cancelled.'),
                'type': 'info',
                'sticky': False,
            }
        }