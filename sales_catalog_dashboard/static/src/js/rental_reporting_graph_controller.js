/** @odoo-module **/

// Commented out to prevent backend loading issues
// The widget will use polling instead to detect product changes

// import { GraphController } from "@web/views/graph/graph_controller";
// import { patch } from "@web/core/utils/patch";

// // Patch the graph controller to add our widget
// patch(GraphController.prototype, {
//     setup() {
//         super.setup();
//         this.productId = null;
//     },
//     
//     /**
//      * Override to detect product selection and update widget
//      */
//     async onWillUpdateProps(nextProps) {
//         await super.onWillUpdateProps(nextProps);
//         this.updateProductWidget();
//     },
//     
//     updateProductWidget() {
//         // Get product from search model
//         const searchModel = this.props.model.searchModel;
//         if (!searchModel) return;
//         
//         const domain = searchModel.domain || [];
//         let productId = null;
//         
//         // Find product_id in domain
//         for (const condition of domain) {
//             if (Array.isArray(condition) && condition.length >= 3) {
//                 if (condition[0] === 'product_id' && condition[1] === '=') {
//                     productId = condition[2];
//                     break;
//                 }
//                 if (condition[0] === 'product_id' && condition[1] === 'in' && Array.isArray(condition[2]) && condition[2].length > 0) {
//                     productId = condition[2][0];
//                     break;
//                 }
//             }
//         }
//         
//         // Check active filters
//         if (!productId) {
//             const activeFilters = searchModel.activeFilters || [];
//             const productFilter = activeFilters.find(f => f.fieldName === 'product_id');
//             if (productFilter && productFilter.value) {
//                 productId = Array.isArray(productFilter.value) ? productFilter.value[0] : productFilter.value;
//             }
//         }
//         
//         // Update if product changed
//         if (productId !== this.productId) {
//             this.productId = productId;
//             // Trigger widget update via event
//             this.env.bus.trigger('rental_reporting:product_changed', { productId });
//         }
//     }
// });

