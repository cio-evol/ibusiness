from odoo import models, fields, api

class ReportColumn(models.Model):
    _inherit = 'account.report.column'

    total_pdc_amount = fields.Float(string='Total PDC Amount')


    def _compute_total_pdc_amount(self):
        for column in self:
            partner = column.report_line_id.partner_id if column.report_line_id else None
            if partner:
                pdc_records = self.env['pdc.cheque'].search([
                    ('partner_id', '=', partner.id)
                ])
                column.total_pdc_amount = sum(pdc_records.mapped('amount'))
            else:
                column.total_pdc_amount = 0.0
