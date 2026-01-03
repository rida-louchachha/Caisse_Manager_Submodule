/** @odoo-module **/

// Simple script to add summary banner when page loads
// This uses vanilla JS to avoid OWL lifecycle issues

document.addEventListener('DOMContentLoaded', function () {
    // Check if we're on subscription page by URL
    if (window.location.href.includes('/subscriptions') || window.location.href.includes('sale.order')) {
        console.log('CM Subscription Alerts: Ready');
    }
});
