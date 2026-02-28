# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError


class PDCReturnWizard(models.TransientModel):
    _name = "pdc.return.wizard"
    _description = "PDC Return Wizard"

    pdc_id = fields.Many2one('pdc.wizard', string="PDC", required=True)
    return_type = fields.Selection([
        ('can_be_bank', 'Can be Bank'),
        ('cant_be_bank', "Can't be Bank")
    ], string="Return Type", required=True, default='can_be_bank')
    
    reason = fields.Text(string="Return Reason", required=True)
    
    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        if self.env.context.get('active_id'):
            res['pdc_id'] = self.env.context.get('active_id')
        return res

    def action_confirm_return(self):
        """Process the PDC return based on selected type"""
        self.ensure_one()
        
        if self.return_type == 'can_be_bank':
            self._return_can_be_bank()
            self.pdc_id.write({'state': 'returned'})
        else:
            self._return_cant_be_bank()
            # Set state to 'returned' when cheque is returned
            # We avoid calling action_cancel() which would delete all entries
            self.pdc_id.write({'state': 'returned'})

        
        return {'type': 'ir.actions.act_window_close'}

    def _return_can_be_bank(self):
        """Return: Payment Journal → Cheque In-Hand (can still be deposited)"""
        pdc = self.pdc_id
        
        if not pdc.env.company.cheque_in_hand:
            raise UserError("Please configure Cheque In-Hand journal!")
        
        cheque_in_hand_account = pdc.env.company.cheque_in_hand.default_account_id
        if not cheque_in_hand_account:
            raise UserError("Please configure default account for Cheque In-Hand journal!")
        
        if not pdc.journal_id:
            raise UserError("Please select a Payment Journal!")
        
        # bank_account = pdc.journal_id.default_account_id
        outbound_accounts = pdc.journal_id._get_journal_outbound_outstanding_payment_accounts()
        if not outbound_accounts:
            raise UserError("Please configure outbound payment method line for Payment Journal!")
        outbound_account = outbound_accounts[0].id

        # if not bank_account:
        #     raise UserError("Please configure default account for Payment Journal!")
        
        # Create journal entry: Bank → Cheque In-Hand
        move_vals = {
            'date': fields.Date.today(),
            'journal_id': pdc.journal_id.id,
            'partner_id': pdc.partner_id.id,
            'ref': f"PDC Return (Can be Bank) - {pdc.memo or 'Cheque'}",
            'move_type': 'entry',
            'pdc_id': pdc.id,
            'line_ids': [
                # Debit: Cheque In-Hand Account (restore cheque)
                (0, 0, {
                    'account_id': cheque_in_hand_account.id,
                    'debit': pdc.payment_amount,
                    'credit': 0,
                    'ref': self.reason,
                    'date': fields.Date.today(),
                    'pdc_id': pdc.id
                }),
                # Credit: Bank Account (remove from bank)
                (0, 0, {
                    'account_id': outbound_account,
                    'debit': 0,
                    'credit': pdc.payment_amount,
                    'ref': self.reason,
                    'date': fields.Date.today(),
                    'pdc_id': pdc.id
                })
            ]
        }
        
        move = self.env['account.move'].create(move_vals)
        move.action_post()

    def _return_cant_be_bank(self):
        """Return: Reverse Customer Debit and Bank Credit (completely returned)
        
        Creates a reversal journal entry without deleting original entries.
        Original entries are kept for audit trail purposes.
        """
        pdc = self.pdc_id
        
        if not pdc.journal_id:
            raise UserError("Please select a Payment Journal!")
        
        # Get customer receivable account
        customer_account = pdc.partner_id.property_account_receivable_id
        if not customer_account:
            raise UserError("Please configure receivable account for customer!")
        
        # Get bank account from payment journal (inbound account)
        inbound_accounts = pdc.journal_id._get_journal_inbound_outstanding_payment_accounts()
        if not inbound_accounts:
            raise UserError("Please configure inbound payment method line for Payment Journal!")
        bank_account = inbound_accounts[0].id
        
        # Create reversal journal entry: Debit Customer, Credit Bank
        # Note: We set pdc_id for tracking, but we do NOT delete original entries
        # Original entries remain for audit trail - only the reversal is created
        move_vals = {
            'date': fields.Date.today(),
            'journal_id': pdc.journal_id.id,
            'partner_id': pdc.partner_id.id,
            'ref': f"PDC Return (Can't be Bank) - {pdc.memo or 'Cheque'} - {self.reason}",
            'move_type': 'entry',
            'pdc_id': pdc.id,  # Keep link for tracking, but original entries won't be deleted
            'line_ids': [
                # Debit: Customer Receivable Account (reverse the original credit)
                (0, 0, {
                    'account_id': customer_account.id,
                    'debit': pdc.payment_amount,
                    'credit': 0,
                    'ref': self.reason,
                    'date': fields.Date.today(),
                    'partner_id': pdc.partner_id.id,
                    'pdc_id': pdc.id
                }),
                # Credit: Bank Account (reverse the original debit)
                (0, 0, {
                    'account_id': bank_account,
                    'debit': 0,
                    'credit': pdc.payment_amount,
                    'ref': self.reason,
                    'date': fields.Date.today(),
                    'partner_id': pdc.partner_id.id,
                    'pdc_id': pdc.id
                })
            ]
        }
        
        move = self.env['account.move'].create(move_vals)
        move.action_post()