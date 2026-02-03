# -*- coding: utf-8 -*-

from odoo import models, fields, api


class PropertyType(models.Model):
    _name = 'property.type'
    _description = 'Property Type'
    _order = 'sequence, name'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(
        string='Type Name',
        required=True,
        tracking=True,
    )
    code = fields.Char(
        string='Code',
        required=True,
        tracking=True,
    )
    sequence = fields.Integer(
        string='Sequence',
        default=10,
    )
    description = fields.Text(
        string='Description',
    )
    parent_id = fields.Many2one(
        'property.type',
        string='Parent Type',
        index=True,
        ondelete='restrict',
    )
    child_ids = fields.One2many(
        'property.type',
        'parent_id',
        string='Child Types',
    )
    property_ids = fields.One2many(
        'property.property',
        'property_type_id',
        string='Properties',
    )
    property_count = fields.Integer(
        string='Property Count',
        compute='_compute_property_count',
    )
    active = fields.Boolean(
        string='Active',
        default=True,
    )
    color = fields.Integer(
        string='Color Index',
    )

    _sql_constraints = [
        ('code_uniq', 'unique(code)', 'The code must be unique!'),
    ]

    @api.depends('property_ids')
    def _compute_property_count(self):
        for record in self:
            record.property_count = len(record.property_ids)

    def name_get(self):
        result = []
        for record in self:
            if record.parent_id:
                name = f"{record.parent_id.name} / {record.name}"
            else:
                name = record.name
            result.append((record.id, name))
        return result
