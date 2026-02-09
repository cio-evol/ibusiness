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
    product_category_id = fields.Many2one(
        'product.category',
        string='Product Category',
        ondelete='set null',
        index=True,
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

    @api.model_create_multi
    def create(self, vals_list):
        if self.env.context.get('skip_product_category_sync'):
            return super().create(vals_list)

        prepared_vals = []
        for vals in vals_list:
            vals = dict(vals)
            if not vals.get('product_category_id'):
                parent_category_id = self._get_parent_product_category_id(vals.get('parent_id'))
                category = self.env['product.category'].with_context(
                    skip_property_category_sync=True
                ).create({
                    'name': vals.get('name'),
                    'parent_id': parent_category_id,
                    'sync_property': True,
                })
                vals['product_category_id'] = category.id
            prepared_vals.append(vals)

        records = super().create(prepared_vals)
        for record in records:
            if record.product_category_id:
                record.product_category_id.with_context(
                    skip_property_category_sync=True
                ).write({
                    'property_type_id': record.id,
                    'sync_property': True,
                })
        return records

    def write(self, vals):
        if self.env.context.get('skip_product_category_sync'):
            return super().write(vals)

        old_categories = {rec.id: rec.product_category_id for rec in self}
        res = super().write(vals)

        for record in self:
            if 'product_category_id' in vals:
                old_category = old_categories.get(record.id)
                new_category = record.product_category_id
                if old_category and old_category.property_type_id == record:
                    old_category.with_context(skip_property_category_sync=True).write({
                        'property_type_id': False,
                    })
                if new_category:
                    new_category.with_context(skip_property_category_sync=True).write({
                        'property_type_id': record.id,
                        'sync_property': True,
                    })
            record._sync_product_category(vals)
        return res

    def _sync_product_category(self, vals=None):
        if self.env.context.get('skip_product_category_sync'):
            return

        fields_changed = set(vals.keys()) if vals else set()
        for record in self:
            category = record.product_category_id
            if not category or not category.sync_property:
                continue

            parent_category_id = False
            if record.parent_id:
                if not record.parent_id.product_category_id:
                    record.parent_id._ensure_product_category()
                parent_category_id = (
                    record.parent_id.product_category_id.id
                    if record.parent_id.product_category_id
                    else False
                )

            update_vals = {}
            if not fields_changed or 'name' in fields_changed:
                update_vals['name'] = record.name
            if not fields_changed or 'parent_id' in fields_changed:
                update_vals['parent_id'] = parent_category_id

            if update_vals:
                category.with_context(skip_property_category_sync=True).write(update_vals)

    def _get_parent_product_category_id(self, parent_id):
        if not parent_id:
            return False
        parent = self.env['property.type'].browse(parent_id)
        if parent and not parent.product_category_id:
            parent._ensure_product_category()
        return parent.product_category_id.id if parent.product_category_id else False

    def _ensure_product_category(self):
        for record in self:
            if record.product_category_id:
                continue
            parent_category_id = False
            if record.parent_id:
                if not record.parent_id.product_category_id:
                    record.parent_id._ensure_product_category()
                parent_category_id = (
                    record.parent_id.product_category_id.id
                    if record.parent_id.product_category_id
                    else False
                )
            category = self.env['product.category'].with_context(
                skip_property_category_sync=True
            ).create({
                'name': record.name,
                'parent_id': parent_category_id,
                'sync_property': True,
            })
            record.with_context(skip_product_category_sync=True).write({
                'product_category_id': category.id,
            })
            category.with_context(skip_property_category_sync=True).write({
                'property_type_id': record.id,
                'sync_property': True,
            })
        return self
