from odoo import models, fields, api, _
from odoo.tools import float_compare, float_round
from odoo.exceptions import ValidationError


class AccountPDCAllocation(models.Model):
    _name = 'account.pdc.allocation'
    _description = 'Account PDC Allocation'

    pdc_id = fields.Many2one('account.pdc', string='PDC', required=True)
    invoice_id = fields.Many2one('account.move', string='Invoice', required=True)
    partner_id = fields.Many2one('res.partner', string='Partner',
                                 compute='_compute_partner_amount', store=True)
    amount = fields.Float(string='Amount', compute='_compute_partner_amount', store=True)
    amount_allocate = fields.Float(string='Amount Allocate', required=True)

    @api.depends('invoice_id')
    def _compute_partner_amount(self):
        """Auto-populate partner when invoice is selected"""
        for record in self:
            record.partner_id = record.invoice_id.partner_id.id
            record.amount = record.invoice_id.amount_residual

    @api.onchange('invoice_id')
    def _onchange_invoice_id(self):
        """Auto-populate amount when invoice is selected"""
        if self.invoice_id:
            # Suggest the residual amount as allocation amount
            if self.invoice_id.amount_residual > 0:
                self.amount_allocate = self.invoice_id.amount_residual

    @api.constrains('amount_allocate', 'invoice_id')
    def _check_amount_allocate(self):
        """Validate that allocated amount doesn't exceed invoice residual"""
        for record in self:
            if record.amount_allocate <= 0:
                raise ValidationError(_('Allocated amount must be greater than zero.'))

            if record.invoice_id and record.amount_allocate > record.invoice_id.amount_residual:
                raise ValidationError(
                    _('Allocated amount (%.2f) cannot exceed invoice residual amount (%.2f) for invoice %s.') %
                    (record.amount_allocate, record.invoice_id.amount_residual, record.invoice_id.name)
                )


class AccountPDCHandoverBreakdown(models.Model):
    _name = 'account.pdc.handover.breakdown'
    _description = 'Account PDC Handover Breakdown'

    pdc_id = fields.Many2one('account.pdc', string='PDC', required=True, ondelete='cascade')
    bill_id = fields.Many2one('account.move', string='Vendor Bill', required=True)
    partner_id = fields.Many2one('res.partner', string='Partner',
                                 compute='_compute_partner_amount', store=True)
    amount = fields.Float(string='Bill Amount', compute='_compute_partner_amount', store=True)
    amount_allocate = fields.Float(string='Amount Allocated', required=True)
    handover_date = fields.Date(string='Handover Date', related='pdc_id.handover_date', store=True)

    @api.depends('bill_id')
    def _compute_partner_amount(self):
        """Auto-populate partner and amount when bill is selected"""
        for record in self:
            record.partner_id = record.bill_id.partner_id.id if record.bill_id else False
            record.amount = record.bill_id.amount_residual if record.bill_id else 0.0

    # @api.constrains('amount_allocate', 'bill_id')
    # def _check_amount_allocate(self):
    #     """Validate that allocated amount doesn't exceed bill residual"""
    #     for record in self:
    #         if record.amount_allocate <= 0:
    #             raise ValidationError(_('Allocated amount must be greater than zero.'))
    #
    #         if record.bill_id and record.amount_allocate > record.bill_id.amount_residual:
    #             raise ValidationError(
    #                 _('Allocated amount (%.2f) cannot exceed bill residual amount (%.2f) for bill %s.') %
    #                 (record.amount_allocate, record.bill_id.amount_residual, record.bill_id.name)
    #             )

