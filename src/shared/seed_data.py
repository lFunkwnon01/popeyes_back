from src.shared import config


SEED_PRODUCTS = [
    {
        "name": "Combo 2 piezas",
        "description": "Pollo frito con acompanamiento y bebida",
        "price": 23.9,
        "category": "Combos",
        "imageUrl": "",
        "active": True,
    },
    {
        "name": "Chicken Sandwich",
        "description": "Sandwich de pollo estilo Popeyes",
        "price": 18.5,
        "category": "Sandwiches",
        "imageUrl": "",
        "active": True,
    },
    {
        "name": "Papas Cajun",
        "description": "Papas sazonadas estilo cajun",
        "price": 8.5,
        "category": "Acompanamientos",
        "imageUrl": "",
        "active": True,
    },
    {
        "name": "Nuggets",
        "description": "Nuggets de pollo crujientes",
        "price": 12.0,
        "category": "Snacks",
        "imageUrl": "",
        "active": True,
    },
    {
        "name": "Gaseosa",
        "description": "Bebida gaseosa fria",
        "price": 6.5,
        "category": "Bebidas",
        "imageUrl": "",
        "active": True,
    },
]


SEED_USERS = [
    {"email": "admin@popeyes.com", "name": "Admin Popeyes", "role": "ADMIN"},
    {"email": "worker@popeyes.com", "name": "Restaurant Worker", "role": "RESTAURANT_WORKER"},
    {"email": "cook@popeyes.com", "name": "Cook Popeyes", "role": "COOK"},
    {"email": "dispatcher@popeyes.com", "name": "Dispatcher Popeyes", "role": "DISPATCHER"},
    {"email": "driver@popeyes.com", "name": "Driver Popeyes", "role": "DELIVERY_DRIVER"},
    {"email": "client@popeyes.com", "name": "Client Popeyes", "role": "CLIENT"},
]

SEED_STORE = {
    "tenantId": config.DEFAULT_TENANT_ID,
    "storeId": config.DEFAULT_STORE_ID,
    "name": "Popeyes Store 001",
    "address": "Av. Demo 123",
    "active": True,
}
