from odoo import models, fields, api
from odoo.exceptions import UserError, ValidationError
from odoo.tools import float_compare, float_round


class AccountDepositWizard(models.TransientModel):
    _name = 'account.deposit.wizard'
    _description = 'Account Deposit Wizard'

    pdc_ids = fields.Many2many('account.pdc', string='PDCs', readonly=True)
    bank_journal_id = fields.Many2one('account.journal', string='Bank Journal',
                                      domain=[('type', '=', 'bank')], required=True)
    bank_account_number = fields.Char(string='Bank Account Number')
    deposit_date = fields.Date(string='Deposit Date', required=True, default=fields.Date.context_today)

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        context = self.env.context
        if context.get('default_pdc_ids'):
            res['pdc_ids'] = [(6, 0, context.get('default_pdc_ids'))]

        return res

    def action_deposit(self):
        if not self.bank_journal_id:
            raise UserError('Bank journal is required for deposit.')

        if self.pdc_ids:
            for pdc in self.pdc_ids:
                pdc.write({
                    'state': 'deposited',
                    'bank_journal_id': self.bank_journal_id.id,
                    'bank_account_number': self.bank_account_number,
                    'deposit_date': self.deposit_date
                })
