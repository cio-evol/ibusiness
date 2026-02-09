from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError


class AccountPDCWizardCheque(models.TransientModel):
    _name = 'account.pdc.wizard.cheque'
    _description = 'PDC Cheque Wizard'

    partner_id = fields.Many2one('res.partner', string='Partner', required=True, readonly=True)
    move_type = fields.Selection([
        ('out_invoice', 'Customer Invoice'),
        ('in_invoice', 'Vendor Bill'),
    ], string='Type', default='out_invoice', readonly=True)
    cheque_line_ids = fields.One2many('account.pdc.wizard.cheque.line', 'wizard_id', string='Cheque Details')
    auto_confirm = fields.Boolean(string='Confirm PDC automatically', default=True,
                                 help="If checked, the PDC will be automatically confirmed after creation.")

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        context = self.env.context

        if context.get('default_move_type'):
            res['move_type'] = context['default_move_type']

        active_ids = context.get('active_ids', [])
        if active_ids:
            invoices = self.env['account.move'].browse(active_ids)
            valid_invoices = invoices.filtered(
                lambda inv: inv.state == 'posted'
                            and inv.payment_state in ('not_paid', 'partial')
                            and inv.amount_residual > 0
            )

            if valid_invoices:
                # Set partner from first invoice
                res['partner_id'] = valid_invoices[0].partner_id.id

        return res

    def action_confirm(self):
        self.ensure_one()

        if not self.cheque_line_ids:
            raise UserError(_('Please add at least one cheque.'))

        pdc_records = []
        for line in self.cheque_line_ids:
            if not line.chq_bank_id:
                raise UserError(_('Please specify the bank for the cheque.'))
            if not line.cheque_number:
                raise UserError(_('Please specify the cheque number.'))

            # Validate based on manual amount or allocations
            if line.use_manual_amount:
                if not line.manual_amount or line.manual_amount <= 0:
                    raise UserError(_('Please enter a valid PDC amount.'))
            else:
                if not line.allocation_ids:
                    raise UserError(_('Please add at least one invoice allocation.'))

            pdc = self.env['account.pdc'].create({
                'partner_id': self.partner_id.id,
                'chq_bank_id': line.chq_bank_id.id,
                'cheque_number': line.cheque_number,
                'cheque_date': line.cheque_date,
                'customer_bank_account': line.customer_bank_account,
                'hand_over_to': line.hand_over_to.id if line.hand_over_to else False,
                'move_type': self.move_type,
                'use_manual_amount': line.use_manual_amount,
                'manual_amount': line.manual_amount if line.use_manual_amount else 0.0,
            })
            pdc_records.append(pdc.id)

            # Only create allocations for non-manual amount PDCs
            if not line.use_manual_amount:
                for allocation in line.allocation_ids:
                    if allocation.amount_allocate > 0:
                        self.env['account.pdc.allocation'].create({
                            'pdc_id': pdc.id,
                            'invoice_id': allocation.invoice_id.id,
                            'partner_id': self.partner_id.id,
                            'amount': allocation.amount,
                            'amount_allocate': allocation.amount_allocate,
                        })

            # Auto-confirm PDC if checkbox is checked
            if self.auto_confirm:
                try:
                    pdc.action_confirm()
                except Exception as e:
                    raise UserError(_('Failed to confirm PDC %s: %s') % (pdc.name, str(e)))

        return {
            'type': 'ir.actions.act_window',
            'name': _('PDC Records'),
            'res_model': 'account.pdc',
            'view_mode': 'list,form',
            'domain': [('id', 'in', pdc_records)],
        }


class AccountPDCWizardChequeLine(models.TransientModel):
    _name = 'account.pdc.wizard.cheque.line'
    _description = 'PDC Cheque Line'

    wizard_id = fields.Many2one('account.pdc.wizard.cheque', required=True, ondelete='cascade')
    chq_bank_id = fields.Many2one('res.bank', string='Cheque Bank', required=True)
    cheque_number = fields.Char(string='Cheque Number', required=True)
    cheque_date = fields.Date(string='Cheque Date', default=fields.Date.today, required=True)
    customer_bank_account = fields.Char(string='Customer Bank Account Number',
                                       help="The customer's bank account number from the cheque")
    hand_over_to = fields.Many2one('res.partner', string='Handed Over To')
    allocation_ids = fields.One2many('account.pdc.wizard.allocation', 'cheque_line_id', string='Allocations')
    total_allocate = fields.Float(string='Total Allocation', compute='_compute_total_allocation', store=True)
    use_manual_amount = fields.Boolean(string='Use Manual Amount', default=False,
                                      help="Check this to enter PDC amount manually instead of using invoice allocations")
    manual_amount = fields.Float(string='PDC Amount',
                                help="Manual PDC amount. If set, this will be used instead of allocated amount")
    move_type = fields.Selection(related='wizard_id.move_type', string='Type')
    partner_id = fields.Many2one(related='wizard_id.partner_id', string='Partner', store=False)

    @api.depends('allocation_ids')
    def _compute_total_allocation(self):
        for record in self:
            record.total_allocate = sum(record.allocation_ids.mapped('amount_allocate'))

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        context = self.env.context

        # Get current invoice from active_id if opening from invoice form
        active_id = context.get('active_id')
        active_model = context.get('active_model')

        if active_model == 'account.move' and active_id:
            invoice = self.env['account.move'].browse(active_id)
            if invoice.exists() and invoice.amount_residual > 0:
                res['allocation_ids'] = [(0, 0, {
                    'invoice_id': invoice.id,
                    'amount_allocate': invoice.amount_residual,
                })]

        return res


class AccountPDCWizardAllocation(models.TransientModel):
    _name = 'account.pdc.wizard.allocation'
    _description = 'PDC Wizard Allocation'

    cheque_line_id = fields.Many2one('account.pdc.wizard.cheque.line', required=True, ondelete='cascade')
    invoice_id = fields.Many2one('account.move', string='Invoice', required=True)
    amount = fields.Float(string='Amount', compute='_compute_amount', store=True)
    amount_allocate = fields.Float(string='Amount Allocate', required=True)

    @api.depends('invoice_id')
    def _compute_amount(self):
        for record in self:
            record.amount = record.invoice_id.amount_residual if record.invoice_id else 0.0

    @api.onchange('invoice_id')
    def _onchange_invoice_id(self):
        if self.invoice_id and self.invoice_id.amount_residual > 0:
            self.amount_allocate = self.invoice_id.amount_residual

    @api.constrains('amount_allocate', 'invoice_id')
    def _check_amount_allocate(self):
        for record in self:
            if record.amount_allocate <= 0:
                raise ValidationError(_('Allocated amount must be greater than zero.'))

            if record.invoice_id and record.amount_allocate > record.invoice_id.amount_residual:
                raise ValidationError(
                    _('Allocated amount (%.2f) cannot exceed invoice residual amount (%.2f) for invoice %s.') %
                    (record.amount_allocate, record.invoice_id.amount_residual, record.invoice_id.name)
                )