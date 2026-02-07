from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError


class AccountMove(models.Model):
    _inherit = "account.move"

    account_pdc_allocation_id = fields.One2many('account.pdc.allocation', 'invoice_id',
                                                string='PDC Allocations')
    account_pdc_ids = fields.Many2many('account.pdc', string='PDCs', compute='_compute_account_pdc_ids')
    account_pdc_count = fields.Integer(string='PDCs', compute='_compute_account_pdc_ids')

    total_pdc_amount = fields.Float(string='PDC Amount', compute='_compute_total_pdc_amount', store=True)

    @api.depends('account_pdc_allocation_id', 'account_pdc_allocation_id.amount_allocate')
    def _compute_total_pdc_amount(self):
        """Compute the total PDC amount allocated to this invoice from all PDCs"""
        for record in self:
            record.total_pdc_amount = sum(record.account_pdc_allocation_id.mapped('amount_allocate'))

    def _compute_account_pdc_ids(self):
        """Compute the PDCs related to this invoice"""
        for record in self:
            pdc_ids = self.env['account.pdc.allocation'].search([('invoice_id', '=', record.id)]).mapped('pdc_id')
            record.account_pdc_ids = pdc_ids
            record.account_pdc_count = len(pdc_ids)

    def action_view_account_pdc(self):
        """Action to view PDCs from smart button"""
        self.ensure_one()
        action = self.env.ref('ns_pdc.action_account_pdc').read()[0]
        action.update({
            'domain': [('id', 'in', self.account_pdc_ids.ids)],
        })
        if self.account_pdc_count == 1:
            action.update({
                'views': [(self.env.ref('ns_pdc.view_account_pdc_form').id, 'form')],
                'res_id': self.account_pdc_ids.id,
            })

        return action

    def pay_by_cheque(self):
        """Open wizard to pay by cheque - allows multiple customers"""
        move_types = self.mapped('move_type')

        # Check if mixing customer and vendor documents
        customer_types = {'out_invoice', 'out_refund'}
        vendor_types = {'in_invoice', 'in_refund', 'in_receipt'}

        has_customer = any(mt in customer_types for mt in move_types)
        has_vendor = any(mt in vendor_types for mt in move_types)

        if has_customer and has_vendor:
            raise UserError(
                _("You cannot mix customer invoices with vendor bills. Please select only customer documents or only vendor documents."))

        # Determine the type for the wizard
        if has_customer:
            wizard_move_type = 'out_invoice'
        elif has_vendor:
            wizard_move_type = 'in_invoice'
        else:
            wizard_move_type = 'out_invoice'

        return {
            'type': 'ir.actions.act_window',
            'name': _('Pay by Cheque'),
            'res_model': 'account.pdc.wizard.cheque',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_move_type': wizard_move_type,
                'active_ids': self.ids,
            }
        }