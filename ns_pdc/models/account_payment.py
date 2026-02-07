from odoo import models, fields, api


class AccountPayment(models.Model):
    _inherit = 'account.payment'

    pdc_id = fields.Many2one('account.pdc', string='PDC Reference', ondelete='cascade')

    is_chq_payment = fields.Boolean(string='Is Cheque Payment', default=False)
    chq_number = fields.Char(string='Cheque Number', tracking=True)
    chq_date = fields.Date(string='Cheque Date', tracking=True)
    chq_bank_id = fields.Many2one("res.bank", string="Cheque Bank", tracking=True)
    bank_account_number = fields.Char(string='Bank Account Number', tracking=True)
    deposit_date = fields.Date(string='Deposited Date', tracking=True)
    handed_over_to_partner = fields.Many2one('res.partner', string="Handed Over To", tracking=True)

    # Handover related fields
    pdc_handover_id = fields.Many2one('account.pdc', string='PDC Handover Reference', ondelete='cascade')
    is_handover_payment = fields.Boolean(string='Is Handover Payment', default=False)

