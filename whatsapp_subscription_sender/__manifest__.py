{
    'name': 'WhatsApp Subscription Sender',
    'version': '3.0',
    'category': 'Sales/Subscriptions',
    'summary': 'Send WhatsApp messages to subscription clients with automated reminders',
    'description': """
        This module allows sending WhatsApp messages to subscription clients.
        Features:
        - Automated monthly payment reminders
        - Automated shutdown warnings for unpaid subscriptions  
        - Bulk sending from subscription list
        - Template messages support (Meta Cloud API)
        - Message history and delivery status tracking
    """,
    'depends': ['sale', 'cm_subscription_alerts'],
    'data': [
        'security/ir.model.access.csv',
        'views/whatsapp_template_views.xml',
        'views/whatsapp_scheduled_message_views.xml',
        'views/whatsapp_message_log_views.xml',
        'views/whatsapp_webhook_config_views.xml',
        'views/whatsapp_chat_views.xml',
        'wizard/whatsapp_sender_wizard_views.xml',
        'views/sale_order_views.xml',
    ],
    'installable': True,
    'application': True,
    'license': 'LGPL-3',
}
