from odoo import models, fields, api, _
from odoo.exceptions import UserError

class AssetAllocationAddQtyWizard(models.TransientModel):
    _name = 'sales.catalog.asset.allocation.add.qty.wizard'
    _description = 'Asset Allocation Add Qty Wizard'

    allocation_id = fields.Many2one('sales.catalog.asset.allocation', string='Allocation', required=True, ondelete='cascade')
    product_id = fields.Many2one('product.product', string='Asset')
    quantity = fields.Float(string='Quantity', default=1.0)
    uom_id = fields.Many2one('uom.uom', string='Unit of Measure')
    destination_property_id = fields.Many2one(
        'product.product',
        string='Newly Allocating Property',
        domain="[('is_property', '=', True)]",
        required=True,
        ondelete='cascade'
    )

    line_ids = fields.One2many('sales.catalog.asset.allocation.add.qty.wizard.line', 'wizard_id', string='Lines')

    def action_confirm(self):
        self.ensure_one()
        
        # Validation: check if quantity matches number of serial numbers
        if self.quantity != len(self.line_ids):
            raise UserError(_("The quantity (%.2f) must match the number of serial numbers added (%d).") % (self.quantity, len(self.line_ids)))

        lot_ids_to_assign = []
        for line in self.line_ids:
            if line.lot_id:
                line.lot_id.write({'property_id': self.destination_property_id.id})
                lot_ids_to_assign.append(line.lot_id.id)

        # Update the parent allocation: quantity, hide Add Qty button, and set THIS line's lots only
        allocation = self.allocation_id
        allocation.write({
            'quantity': self.quantity,
            'add_qty_confirmed': True,
            'lot_ids': [(6, 0, lot_ids_to_assign)],
        })

        # Reload the list view so the Add Qty button is hidden for this record
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'sales.catalog.asset.allocation',
            'view_mode': 'list',
            'views': [(False, 'list')],
            'target': 'current',
            'context': self.env.context,
        }

class AssetAllocationAddQtyWizardLine(models.TransientModel):
    _name = 'sales.catalog.asset.allocation.add.qty.wizard.line'
    _description = 'Asset Allocation Add Qty Wizard Line'

    wizard_id = fields.Many2one('sales.catalog.asset.allocation.add.qty.wizard', string='Wizard', ondelete='cascade')
    product_id = fields.Many2one('product.product', string='Product')

    lot_id = fields.Many2one(
        'stock.lot',
        string='Product Serial Number',
        domain="[('product_id', '=', product_id)]",
        ondelete='cascade'
    )
    prev_property_id = fields.Many2one(
        'product.product',
        related='lot_id.property_id',
        string='Previous Allocated Property',
        readonly=True
    )
