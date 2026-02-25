from odoo import models, fields, api
from odoo.exceptions import UserError

class ZiwoActiveForm(models.Model):
    _name = 'ziwo.active.form'
    _description = 'Ziwo Active Form'
    
    model_id = fields.Many2one('ir.model', string='Model', domain=[('model', 'in', ['res.partner','crm.lead','helpdesk.ticket', 'sale.order', 'project.task'])])
    name = fields.Char(string='Name', related='model_id.name', readonly=True)
    action = fields.Selection(selection=[('new', 'New'), ('existing', 'Existing')], string='Action')

    @api.constrains('model_id')
    def _check_model_id(self):
        for record in self:
            if record.model_id:
                if self.env['ziwo.active.form'].sudo().search_count([('model_id','=',record.model_id.id)]) > 1:
                    raise UserError("Active form already exists")
    
    @api.onchange('model_id')
    def _onchange_model_id(self):
        if self.model_id:
            if self.model_id.model in ['res.partner']:
                self.action = 'existing'
            else:
                self.action = 'new'