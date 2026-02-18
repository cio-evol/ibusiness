# Rental Reporting Enhancement

This module adds a product image and pie chart widget to the Rental Reporting view in Odoo.

## Features

1. **Product Image Display**: Shows a large, responsive product image that scales to fit its container
2. **Pie Chart Visualization**: Displays rental status breakdown (profit/utilization) for the selected product
3. **Dynamic Updates**: Chart and image update based on the currently selected/filtered product

## How It Works

### Architecture

1. **Model Extension** (`models/rental_report.py`):
   - Extends `sale.rental.report` model
   - Adds `get_product_chart_data()` method that aggregates rental data by status
   - Calculates profit, revenue, cost, and utilization metrics

2. **Controller** (`controllers/rental_reporting_controller.py`):
   - JSON endpoint: `/sales_catalog_dashboard/rental_reporting/chart_data`
   - Returns chart data and product information for the selected product

3. **OWL Component** (`static/src/js/rental_reporting_widget.js`):
   - Custom field widget that displays product image and pie chart
   - Uses Chart.js for pie chart rendering
   - Automatically updates when product selection changes

4. **View** (`views/rental_reporting_enhanced_views.xml`):
   - Creates a custom form view that combines graph with sidebar widget
   - Can be accessed via "Rental Analysis Enhanced" action

## Usage

### Method 1: Using the Enhanced View

1. Go to **Sales → Reporting → Rental Analysis Enhanced**
2. Filter or search by a specific product
3. The product image and pie chart will appear in the sidebar

### Method 2: Adding to Existing Rental Report

The widget can be added to any view by using:
```xml
<field name="product_id" widget="rental_reporting_widget"/>
```

## Technical Details

### Chart Data Structure

The pie chart displays rental status breakdown:
- **Labels**: Order states (draft, sent, sale, done, etc.)
- **Values**: Revenue amount per status
- **Colors**: Predefined color palette

### Image Handling

- Uses Odoo's image field (`image_128`)
- Responsive with `object-fit: contain` to maintain aspect ratio
- Falls back to placeholder if no image available

### CSS Layout

- Flexbox layout for responsive design
- Sidebar width: 300-400px (adjustable)
- Image container: 200-400px height
- Chart container: 300px height

## Files Structure

```
sales_catalog_dashboard/
├── controllers/
│   ├── __init__.py
│   └── rental_reporting_controller.py  # JSON endpoint
├── models/
│   └── rental_report.py                 # Data aggregation
├── static/src/
│   ├── js/
│   │   └── rental_reporting_widget.js  # OWL component
│   ├── css/
│   │   └── rental_reporting_widget.css # Styles
│   └── xml/
│       └── rental_reporting_widget.xml # Template
└── views/
    └── rental_reporting_enhanced_views.xml  # View definitions
```

## Integration Points

The enhancement hooks into:
- **Rental Report Model**: `sale.rental.report`
- **Rental Report Action**: `sale_renting.action_rental_report`
- **Product Model**: `product.product` (for image and data)

## Customization

### Changing Chart Type

Edit `static/src/js/rental_reporting_widget.js` and change:
```javascript
type: 'pie'  // to 'bar', 'line', 'doughnut', etc.
```

### Modifying Data Aggregation

Edit `models/rental_report.py` method `get_product_chart_data()` to change:
- Status breakdown logic
- Profit calculation
- Utilization metrics

### Styling

Edit `static/src/css/rental_reporting_widget.css` to customize:
- Layout dimensions
- Colors
- Responsive breakpoints

## Requirements

- Odoo 17+
- `sale_renting` module installed
- Chart.js (loaded automatically via Odoo's asset system)

## Notes

- The widget automatically detects product selection from the record context
- Chart updates when product filter changes
- Image loads asynchronously
- Chart.js is loaded on-demand to avoid performance impact

