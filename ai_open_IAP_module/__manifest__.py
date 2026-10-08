{
    "name": "AI Open IAP Replacement",
    "summary": "Select the AI connection used by the local IAP replacement",
    "author": "mytime.click",
    "website": "https://github.com/OCA/ai",
    "category": "Productivity",
    "version": "20.0.1.0.5",
    "license": "AGPL-3",
    "depends": [
        "ai_connection",
        "ai_private",
    ],
    "data": [
        "data/ai_connection_data.xml",
        "views/ai_connection_views.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "ai_open_IAP_module/static/src/views/ai_connection_list_view.js",
            "ai_open_IAP_module/static/src/views/ai_connection_list_view.xml",
            "ai_open_IAP_module/static/src/views/ai_connection_list_view.scss",
        ],
    },
}
