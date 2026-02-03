# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import UserError


class AssetAssignmentWizard(models.TransientModel):
    _name = 'asset.assignment.wizard'
    _description = 'Quick Asset Assignment Wizard'

    asset_ids = fields.Many2many(
        'product.template',
        string='Assets',
        domain=[('is_asset', '=', True), ('asset_state', 'in', ['new', 'available'])],
        required=True,
    )
    property_id = fields.Many2one(
        'property.property',
        string='Property',
        required=True,
        domain=[('state', '=', 'active')],
    )
    assigned_to_id = fields.Many2one(
        'res.users',
        string='Assigned To',
    )
    assignment_date = fields.Date(
        string='Assignment Date',
        default=fields.Date.today,
        required=True,
    )
    expected_return_date = fields.Date(
        string='Expected Return Date',
    )
    condition_on_assignment = fields.Selection([
        ('new', 'New'),
        ('excellent', 'Excellent'),
        ('good', 'Good'),
        ('fair', 'Fair'),
        ('poor', 'Poor'),
    ], string='Condition', default='good', required=True)
    notes = fields.Text(string='Notes')

    def action_assign(self):
        self.ensure_one()
        if not self.asset_ids:
            raise UserError(_('Please select at least one asset.'))

        assignments = self.env['asset.assignment']
        for asset in self.asset_ids:
            assignment = self.env['asset.assignment'].create({
                'asset_id': asset.id,
                'property_id': self.property_id.id,
                'assigned_to_id': self.assigned_to_id.id if self.assigned_to_id else False,
                'assignment_date': self.assignment_date,
                'expected_return_date': self.expected_return_date,
                'condition_on_assignment': self.condition_on_assignment,
                'assignment_notes': self.notes,
            })
            assignment.action_confirm()
            assignments |= assignment

        return {
            'name': _('Created Assignments'),
            'type': 'ir.actions.act_window',
            'res_model': 'asset.assignment',
            'view_mode': 'list,form',
            'domain': [('id', 'in', assignments.ids)],
        }


class AssetBulkReturnWizard(models.TransientModel):
    _name = 'asset.bulk.return.wizard'
    _description = 'Bulk Asset Return Wizard'

    assignment_ids = fields.Many2many(
        'asset.assignment',
        string='Assignments',
        domain=[('state', '=', 'assigned')],
        required=True,
    )
    return_date = fields.Date(
        string='Return Date',
        default=fields.Date.today,
        required=True,
    )
    condition_on_return = fields.Selection([
        ('excellent', 'Excellent'),
        ('good', 'Good'),
        ('fair', 'Fair'),
        ('poor', 'Poor'),
        ('damaged', 'Damaged'),
    ], string='Condition on Return', default='good', required=True)
    notes = fields.Text(string='Return Notes')

    def action_return(self):
        self.ensure_one()
        if not self.assignment_ids:
            raise UserError(_('Please select at least one assignment.'))

        for assignment in self.assignment_ids:
            assignment.write({
                'actual_return_date': self.return_date,
                'condition_on_return': self.condition_on_return,
                'return_notes': self.notes,
            })
            assignment.action_return()

        return {'type': 'ir.actions.act_window_close'}
