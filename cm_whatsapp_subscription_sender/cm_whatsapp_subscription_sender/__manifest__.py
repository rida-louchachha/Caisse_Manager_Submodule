{
    'name': 'Social Inbox',
    'version': '5.0',
    'category': 'Sales/Subscriptions',
    'summary': 'Unified inbox for WhatsApp, Instagram, SMS, Email and more - like GoHighLevel',
    'description': """
        Unified Social Inbox - Multi-Channel Conversations
        ===================================================
        
        Features:
        - 💬 WhatsApp, 📸 Instagram, 📱 SMS, ✉️ Email - All in one place
        - GHL-style unified conversation view
        - Channel badges on each message
        - Configurable social media channels
        - Automated messaging and templates
        - Two-way communication support
    """,
    'depends': ['sale', 'whatsapp', 'cm_subscription_alerts'],
    'data': [
        'security/ir.model.access.csv',
        'data/social_channel_data.xml',
        'views/whatsapp_inbox_views.xml',
        'views/whatsapp_scheduled_message_views.xml',
        'views/whatsapp_message_log_views.xml',
        'views/whatsapp_chat_views.xml',
        'views/social_channel_views.xml',
        'wizard/whatsapp_sender_wizard_views.xml',
        'views/sale_order_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'cm_whatsapp_subscription_sender/static/src/css/whatsapp_chat.css',
            'cm_whatsapp_subscription_sender/static/src/js/whatsapp_chat.js',
            'cm_whatsapp_subscription_sender/static/src/js/whatsapp_chat_widget.js',
            'cm_whatsapp_subscription_sender/static/src/xml/whatsapp_chat_templates.xml',
            'cm_whatsapp_subscription_sender/static/src/xml/whatsapp_chat_widget.xml',
        ],
    },
    'installable': True,
    'application': True,
    'license': 'LGPL-3',
}
