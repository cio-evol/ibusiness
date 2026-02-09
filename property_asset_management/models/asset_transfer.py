# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError


class AssetTransfer(models.Model):
    _name = 'asset.transfer'
    _description = 'Equipment Internal Transfer'
    _order = 'transfer_date desc, id desc'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(
        string='Reference',
        required=True,
        copy=False,
        readonly=True,
        default=lambda self: _('New'),
    )
    transfer_date = fields.Date(
        string='Transfer Date',
        default=fields.Date.today,
        required=True,
        tracking=True,
    )
    source_property_id = fields.Many2one(
        'product.category',
        string='From Property',
        required=True,
        tracking=True,
        domain=[('sync_property', '=', True)],
    )
    destination_property_id = fields.Many2one(
        'product.category',
        string='To Property',
        required=True,
        tracking=True,
        domain=[('sync_property', '=', True)],
    )
    transfer_line_ids = fields.One2many(
        'asset.transfer.line',
        'transfer_id',
        string='Transfer Lines',
    )
    transferred_by_id = fields.Many2one(
        'res.users',
        string='Transferred By',
        default=lambda self: self.env.user,
        tracking=True,
    )
    reason = fields.Text(string='Reason / Notes')
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        required=True,
        default=lambda self: self.env.company,
    )
    state = fields.Selection([
        ('draft', 'Draft'),
        ('confirmed', 'Confirmed'),
        ('done', 'Done'),
        ('cancelled', 'Cancelled'),
    ], string='Status', default='draft', tracking=True, required=True)

    line_count = fields.Integer(
        string='Equipment Count',
        compute='_compute_line_count',
    )

    @api.depends('transfer_line_ids')
    def _compute_line_count(self):
        for record in self:
            record.line_count = len(record.transfer_line_ids)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code('asset.transfer') or _('New')
        return super().create(vals_list)

    @api.constrains('source_property_id', 'destination_property_id')
    def _check_properties(self):
        for record in self:
            if record.source_property_id == record.destination_property_id:
                raise ValidationError(
                    _('Source and destination property/room cannot be the same.')
                )

    def action_confirm(self):
        for record in self:
            if not record.transfer_line_ids:
                raise UserError(_('Please add at least one equipment to transfer.'))
            # Validate all assets are currently assigned to the source property
            for line in record.transfer_line_ids:
                active_assignment = self.env['asset.assignment'].search([
                    ('asset_id', '=', line.asset_id.id),
                    ('property_category_id', '=', record.source_property_id.id),
                    ('state', '=', 'assigned'),
                ], limit=1)
                if not active_assignment:
                    raise UserError(
                        _('Asset "%s" is not currently assigned to "%s". '
                          'Please check and update the transfer lines.') %
                        (line.asset_id.name, record.source_property_id.name)
                    )
                line.current_assignment_id = active_assignment.id
            record.write({'state': 'confirmed'})

    def action_done(self):
        for record in self:
            for line in record.transfer_line_ids:
                # Return from source property
                if line.current_assignment_id and line.current_assignment_id.state == 'assigned':
                    line.current_assignment_id.write({
                        'actual_return_date': record.transfer_date,
                        'return_notes': _('Transferred to %s via %s') % (
                            record.destination_property_id.name,
                            record.name,
                        ),
                    })
                    line.current_assignment_id.action_return()

                # Create new assignment at destination
                new_assignment = self.env['asset.assignment'].create({
                    'asset_id': line.asset_id.id,
                    'property_category_id': record.destination_property_id.id,
                    'assigned_to_id': record.transferred_by_id.id,
                    'assignment_date': record.transfer_date,
                    'assignment_notes': _('Transferred from %s via %s') % (
                        record.source_property_id.name,
                        record.name,
                    ),
                    'condition_on_assignment': 'good',
                })
                new_assignment.action_confirm()

            record.write({'state': 'done'})
            record.message_post(
                body=_('Transfer completed. %d equipment(s) moved from "%s" to "%s".') % (
                    len(record.transfer_line_ids),
                    record.source_property_id.name,
                    record.destination_property_id.name,
                ),
            )

    def action_cancel(self):
        for record in self:
            if record.state == 'done':
                raise UserError(_('Cannot cancel a completed transfer.'))
            record.write({'state': 'cancelled'})

    def action_draft(self):
        for record in self:
            if record.state == 'done':
                raise UserError(_('Cannot reset a completed transfer to draft.'))
            record.write({'state': 'draft'})


class AssetTransferLine(models.Model):
    _name = 'asset.transfer.line'
    _description = 'Equipment Transfer Line'

    transfer_id = fields.Many2one(
        'asset.transfer',
        string='Transfer',
        required=True,
        ondelete='cascade',
    )
    asset_id = fields.Many2one(
        'product.template',
        string='Equipment',
        required=True,
        domain="[('is_asset', '=', True), ('current_property_category_id', '=', parent.source_property_id)]",
    )
    asset_code = fields.Char(
        related='asset_id.asset_code',
        string='Asset Code',
        store=True,
    )
    asset_category_id = fields.Many2one(
        related='asset_id.asset_category_id',
        string='Asset Category',
        store=True,
    )
    source_property_id = fields.Many2one(
        related='transfer_id.source_property_id',
        string='From',
        store=True,
    )
    destination_property_id = fields.Many2one(
        related='transfer_id.destination_property_id',
        string='To',
        store=True,
    )
    current_assignment_id = fields.Many2one(
        'asset.assignment',
        string='Current Assignment',
        readonly=True,
    )
    notes = fields.Text(string='Notes')
