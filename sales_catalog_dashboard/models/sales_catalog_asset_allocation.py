from odoo import models, fields, api, _

class SalesCatalogAssetAllocation(models.Model):
    _name = 'sales.catalog.asset.allocation'
    _description = 'Sales Catalog Asset Allocation'

    parent_product_id = fields.Many2one(
        'product.product', 
        string='Building/Property', 
        ondelete='cascade', 
        required=True,
        readonly=True
    )
    asset_product_id = fields.Many2one(
        'product.product',
        string='Asset',
        required=True,
        domain="[('categ_id.name', 'ilike', 'Equipment')]"
    )
    quantity = fields.Float(string='Quantity', default=1.0, required=True, readonly=True)

    add_qty_confirmed = fields.Boolean(
        string='Add Qty Confirmed',
        default=False,
        help='When True, the Add Qty button is hidden after the add qty wizard was confirmed.'
    )
    
    asset_category_id = fields.Many2one(
        'product.category', 
        related='asset_product_id.categ_id', 
        string='Category', 
        readonly=True
    )
    uom_id = fields.Many2one(
        'uom.uom', 
        related='asset_product_id.uom_id', 
        string='Unit of Measure', 
        readonly=True
    )

    # Stored lots for this allocation line only (so same product on 2 lines show different lots)
    lot_ids = fields.Many2many(
        'stock.lot',
        'sales_catalog_asset_allocation_lot_rel',
        'allocation_id',
        'lot_id',
        string='Lots/Serials',
        help='Lots/serials assigned to this allocation line. Each line has its own set; lots are not merged across lines.',
    )

    def action_add_assets(self):
        self.ensure_one()
        return {
            'name': _('Add Quantity & Serial Numbers'),
            'type': 'ir.actions.act_window',
            'res_model': 'sales.catalog.asset.allocation.add.qty.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_allocation_id': self.id,
                'default_destination_property_id': self.parent_product_id.id,
                'default_product_id': self.asset_product_id.id,
                'default_uom_id': self.uom_id.id,
            }
        }
