from odoo import models, fields, api, _
from odoo.exceptions import UserError


class AccountPDCReturnWizard(models.TransientModel):
    _name = 'account.pdc.return.wizard'
    _description = 'PDC Return Wizard'

    pdc_id = fields.Many2one('account.pdc', string='PDC', required=True, readonly=True)
    return_date = fields.Date(string='Return Date', required=True, default=fields.Date.context_today)
    return_reason = fields.Text(string='Return Reason', help="Reason for cheque return")

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        context = self.env.context

        if context.get('default_pdc_id'):
            pdc = self.env['account.pdc'].browse(context['default_pdc_id'])
            res['pdc_id'] = pdc.id

        return res

    def action_confirm_return(self):
        """Process the PDC return with the specified date"""
        self.ensure_one()

        if not self.return_date:
            raise UserError(_('Return date is required.'))

        # Call the PDC return processing method with the return date
        return self.pdc_id.process_return(self.return_date, self.return_reason)