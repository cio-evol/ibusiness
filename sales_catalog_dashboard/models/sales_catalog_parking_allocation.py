from odoo import models, fields, api, _

class SalesCatalogParkingAllocation(models.Model):
    _name = 'sales.catalog.parking.allocation'
    _description = 'Sales Catalog Parking Allocation'

    parent_product_id = fields.Many2one(
        'product.product',
        string='Building/Property',
        ondelete='cascade',
        required=True,
        readonly=True
    )
    parking_product_id = fields.Many2one(
        'product.product',
        string='Parking',
        required=True,
        domain="[('categ_id.name', 'ilike', 'Parking')]"
    )
    quantity = fields.Float(string='Quantity', default=1.0, required=True, readonly=True)

    add_qty_confirmed = fields.Boolean(
        string='Add Qty Confirmed',
        default=False,
        help='When True, the Add Qty button is hidden after the add qty wizard was confirmed.'
    )

    parking_category_id = fields.Many2one(
        'product.category',
        related='parking_product_id.categ_id',
        string='Category',
        readonly=True
    )
    uom_id = fields.Many2one(
        'uom.uom',
        related='parking_product_id.uom_id',
        string='Unit of Measure',
        readonly=True
    )

    lot_ids = fields.Many2many(
        'stock.lot',
        'sales_catalog_parking_allocation_lot_rel',
        'allocation_id',
        'lot_id',
        string='Lots/Serials',
        help='Lots/serials assigned to this parking allocation line.',
    )

    def action_add_parking(self):
        self.ensure_one()
        return {
            'name': _('Add Quantity & Serial Numbers'),
            'type': 'ir.actions.act_window',
            'res_model': 'sales.catalog.parking.allocation.add.qty.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_allocation_id': self.id,
                'default_destination_property_id': self.parent_product_id.id,
                'default_product_id': self.parking_product_id.id,
                'default_uom_id': self.uom_id.id,
            }
        }
