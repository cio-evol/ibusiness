# -*- coding: utf-8 -*-
# Part of Softhealer Technologies.
from odoo import api, fields, models


class AccountInvoice(models.Model):
    _inherit = "account.move"

    is_boolean = fields.Boolean(compute="_compute_is_boolean")
    payment_date = fields.Date(string='Payment Date', )
    payment_amount = fields.Monetary("Payment Amount", tracking=True)

    @api.depends("pdc_payment_ids", "pdc_payment_ids.state")
    def _compute_is_boolean(self):
        for rec in self:
            rec.is_boolean = bool(
                rec.pdc_payment_ids.filtered(lambda x: x.state in ("registered", "deposited"))
            )

    def open_pdc_payment(self):
        action = self.env["ir.actions.act_window"]._for_xml_id("sh_pdc.sh_pdc_payment_menu_action")
        action["domain"] = [("id", "in", self.pdc_payment_ids.ids)]
        return action

    def _compute_pdc_payment(self):
        for rec in self:
            rec.pdc_payment_count = len(self.pdc_payment_ids)

    pdc_id = fields.Many2one('pdc.wizard')
    pdc_payment_ids = fields.Many2many(
        'pdc.wizard', compute='_compute_pdc_payment_invoice',search='_search_pdc_payment_ids',)
    pdc_payment_count = fields.Integer(
        "Pdc payment count", compute='_compute_pdc_payment')
    total_pdc_payment = fields.Monetary("Total ", compute='_compute_total_pdc')
    total_pdc_pending = fields.Monetary(
        "Total Pending", compute='_compute_total_pdc')
    total_pdc_cancel = fields.Monetary(
        "Total Cancel", compute='_compute_total_pdc')
    total_pdc_received = fields.Monetary(
        "Total Received", compute='_compute_total_pdc')
    sh_pdc_status = fields.Selection([('draft', 'Draft'), ('registered', 'Registered'), ('returned', 'Returned'),
                              ('deposited', 'Deposited'), ('bounced', 'Bounced'), ('done', 'Done'), ('cancel', 'Cancelled')], string="PDC Status",store=True)
                              # ('deposited', 'Deposited'), ('bounced', 'Bounced'), ('done', 'Done'), ('cancel', 'Cancelled')], string="PDC Status",compute='_compute_latest_pdc_payment_status',store=True)

    balance_payment = fields.Monetary(
        "Balance Payment", compute='_compute_total_pdc')
    # @api.depends('pdc_payment_ids.state')
    # def _compute_latest_pdc_payment_status(self):
    #     for rec in self:
    #         rec.sh_pdc_status = False
    #         if rec.pdc_payment_ids:
    #             rec.sh_pdc_status = rec.pdc_payment_ids[-1].state


    @api.depends('pdc_payment_ids.state')
    def _compute_total_pdc(self):
        for rec in self:
            rec.total_pdc_payment = 0.0
            rec.total_pdc_pending = 0.0
            rec.total_pdc_cancel = 0.0
            rec.total_pdc_received = 0.0
            if rec.pdc_payment_ids:
                for pdc_payment in rec.pdc_payment_ids:
                    if pdc_payment.state in ('done'):
                        rec.total_pdc_received += pdc_payment.payment_amount
                    elif pdc_payment.state in ('cancel'):
                        rec.total_pdc_cancel += pdc_payment.payment_amount
                    else:
                        rec.total_pdc_pending += pdc_payment.payment_amount
            rec.total_pdc_payment = rec.total_pdc_pending + \
                rec.total_pdc_received + rec.total_pdc_cancel
            rec.balance_payment =  rec.amount_residual - rec.total_pdc_payment

    def _compute_pdc_payment_invoice(self):
        self.pdc_payment_ids = False
        for move in self:
            pdcs = self.env["pdc.wizard"].search([
                '|', ('invoice_id', '=', move.id), ('invoice_ids.id', '=', move.id)
            ])
            if pdcs:
                move.pdc_payment_ids = [(6, 0, pdcs.ids)]
                
                
    def _search_pdc_payment_ids(self, operator, value):
        pdcs = self.env['pdc.wizard'].search([('id', operator, value)])
        if pdcs:
            move_ids = pdcs.mapped('invoice_ids.id') + pdcs.mapped('invoice_id.id')
            return [('id', 'in', move_ids)]
        return [('id', '=', False)]

    def action_update_latest_pdc_status(self):
        for rec in self:
            rec.sh_pdc_status = False
            if rec.pdc_payment_ids:
                rec.sh_pdc_status = rec.pdc_payment_ids[-1].state

    def sh_pdc_wizard_action(self):
        view = self.env.ref("sh_pdc.sh_pdc_payment_form_view", raise_if_not_found=False)
        return {
            "name": "PDC",
            "type": "ir.actions.act_window",
            "view_mode": "form",
            "res_model": "pdc.wizard",
            "views": [(view.id if view else False, "form")],
            "target": "new",
        }

    # def _compute_payments_widget_to_reconcile_info(self):
    #     """Override to exclude PDC payments that are not in 'done' status"""
    #     super()._compute_payments_widget_to_reconcile_info()
    #
    #     for move in self:
    #         if move.invoice_outstanding_credits_debits_widget and move.invoice_outstanding_credits_debits_widget.get('content'):
    #             # Filter out PDC payments that are not in 'done' status
    #             filtered_content = []
    #             for item in move.invoice_outstanding_credits_debits_widget['content']:
    #                 # Check if this line is from a PDC payment
    #                 line = self.env['account.move.line'].browse(item['id'])
    #                 if line.pdc_id and line.pdc_id.state != 'done':
    #                     # Skip PDC payments that are not done
    #                     continue
    #                 filtered_content.append(item)
    #
    #             # Update the widget content
    #             move.invoice_outstanding_credits_debits_widget['content'] = filtered_content
    #
    #             # If no content left, hide the widget
    #             if not filtered_content:
    #                 move.invoice_outstanding_credits_debits_widget = False
    #                 move.invoice_has_outstanding = False