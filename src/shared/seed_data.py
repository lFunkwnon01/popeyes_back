from src.shared import config


# === 3 TENANTS (una sede = un tenant, identificado por distrito) ===
# Cada tenant tiene su propio admin + sus propios productos exclusivos.
# Algunos productos son compartidos entre tenants (los "core" del menú).
SEED_STORES = [
    {
        "tenantId": "popeyes-miraflores",
        "name": "Popeyes Miraflores",
        "address": "Av. Larco 345, Miraflores, Lima",
        "active": True,
    },
    {
        "tenantId": "popeyes-surco",
        "name": "Popeyes Surco",
        "address": "Av. Caminos del Inca 1234, Surco, Lima",
        "active": True,
    },
    {
        "tenantId": "popeyes-barranco",
        "name": "Popeyes Barranco",
        "address": "Jr. Bolognesi 567, Barranco, Lima",
        "active": True,
    },
]


# === USERS ===
# - 1 ADMIN por tenant (cada admin maneja SOLO su tenant/sede)
# - 1 worker (RESTAURANT_WORKER, COOK, DISPATCHER, DELIVERY_DRIVER) por tenant
# - 1 CLIENT global (sin tenantId fijo: pide en cualquier sede)
SEED_USERS = [
    # Miraflores
    {"email": "admin.miraflores@popeyes.pe", "name": "Maria Admin Miraflores", "role": "ADMIN", "tenantId": "popeyes-miraflores"},
    {"email": "worker.miraflores@popeyes.pe", "name": "Carlos Recepcionista", "role": "RESTAURANT_WORKER", "tenantId": "popeyes-miraflores"},
    {"email": "cook.miraflores@popeyes.pe", "name": "Juan Cocinero", "role": "COOK", "tenantId": "popeyes-miraflores"},
    {"email": "dispatcher.miraflores@popeyes.pe", "name": "Ana Empacadora", "role": "DISPATCHER", "tenantId": "popeyes-miraflores"},
    {"email": "driver.miraflores@popeyes.pe", "name": "Luis Repartidor", "role": "DELIVERY_DRIVER", "tenantId": "popeyes-miraflores"},
    # Surco
    {"email": "admin.surco@popeyes.pe", "name": "Roberto Admin Surco", "role": "ADMIN", "tenantId": "popeyes-surco"},
    {"email": "worker.surco@popeyes.pe", "name": "Sofia Recepcionista", "role": "RESTAURANT_WORKER", "tenantId": "popeyes-surco"},
    {"email": "cook.surco@popeyes.pe", "name": "Miguel Cocinero", "role": "COOK", "tenantId": "popeyes-surco"},
    {"email": "dispatcher.surco@popeyes.pe", "name": "Patricia Empacadora", "role": "DISPATCHER", "tenantId": "popeyes-surco"},
    {"email": "driver.surco@popeyes.pe", "name": "Andres Repartidor", "role": "DELIVERY_DRIVER", "tenantId": "popeyes-surco"},
    # Barranco
    {"email": "admin.barranco@popeyes.pe", "name": "Elena Admin Barranco", "role": "ADMIN", "tenantId": "popeyes-barranco"},
    {"email": "worker.barranco@popeyes.pe", "name": "Diego Recepcionista", "role": "RESTAURANT_WORKER", "tenantId": "popeyes-barranco"},
    {"email": "cook.barranco@popeyes.pe", "name": "Lucia Cocinera", "role": "COOK", "tenantId": "popeyes-barranco"},
    {"email": "dispatcher.barranco@popeyes.pe", "name": "Fernando Empacador", "role": "DISPATCHER", "tenantId": "popeyes-barranco"},
    {"email": "driver.barranco@popeyes.pe", "name": "Carmen Repartidora", "role": "DELIVERY_DRIVER", "tenantId": "popeyes-barranco"},
    # Cliente global (sin tenantId fijo, puede pedir en cualquier sede)
    {"email": "cliente@popeyes.pe", "name": "Cliente Popeyes", "role": "CLIENT", "tenantId": ""},
]


# === PRODUCTOS POR TENANT ===
# Estructura: { "popeyes-miraflores": [producto1, producto2, ...], ... }
SEED_PRODUCTS_BY_TENANT = {
    "popeyes-miraflores": [
        # Productos exclusivos de Miraflores
        {"name": "Combo Familiar Miraflores", "description": "10 piezas + 2 papas grandes + 4 bebidas (especial Miraflores)", "price": 99.90, "category": "Combos", "imageUrl": "", "active": True},
        {"name": "Pollo a la Brasa Miraflores", "description": "Pollo a la brasa estilo peruano, exclusivo de esta sede", "price": 45.00, "category": "Pollos", "imageUrl": "", "active": True},
        # Productos compartidos (también en otras sedes)
        {"name": "Bucket 8 Piezas", "description": "8 piezas de pollo crispy sazonado", "price": 64.90, "category": "Buckets", "imageUrl": "", "active": True},
        {"name": "Bucket 12 Piezas", "description": "12 piezas para compartir", "price": 89.90, "category": "Buckets", "imageUrl": "", "active": True},
        {"name": "Classic Chicken Sandwich", "description": "Pollo crispy, pepinillo y salsa mayo", "price": 19.90, "category": "Sandwiches", "imageUrl": "", "active": True},
        {"name": "Spicy Chicken Sandwich", "description": "Sandwich de pollo picante", "price": 21.90, "category": "Sandwiches", "imageUrl": "", "active": True},
        {"name": "Papas Cajun Grande", "description": "Papas fritas sazonadas estilo cajún", "price": 12.90, "category": "Sides", "imageUrl": "", "active": True},
        {"name": "Chicken Tenders (6 unid.)", "description": "Tiras de pollo empanizado crujiente", "price": 29.90, "category": "Pollos", "imageUrl": "", "active": True},
        {"name": "Coca-Cola 500ml", "description": "Gaseosa bien fría", "price": 7.50, "category": "Bebidas", "imageUrl": "", "active": True},
    ],
    "popeyes-surco": [
        # Productos exclusivos de Surco
        {"name": "Combo Pareja Surco", "description": "2 piezas + papas para compartir + 2 bebidas (especial Surco)", "price": 39.90, "category": "Combos", "imageUrl": "", "active": True},
        {"name": "Alitas Picantes Surco", "description": "12 alitas picantes con dip de blue cheese", "price": 35.00, "category": "Pollos", "imageUrl": "", "active": True},
        {"name": "Pie de Chocolate Surco", "description": "Pie de chocolate exclusivo de Surco", "price": 12.00, "category": "Postres", "imageUrl": "", "active": True},
        # Productos compartidos
        {"name": "Bucket 8 Piezas", "description": "8 piezas de pollo crispy sazonado", "price": 64.90, "category": "Buckets", "imageUrl": "", "active": True},
        {"name": "Bucket 12 Piezas", "description": "12 piezas para compartir", "price": 89.90, "category": "Buckets", "imageUrl": "", "active": True},
        {"name": "Classic Chicken Sandwich", "description": "Pollo crispy, pepinillo y salsa mayo", "price": 19.90, "category": "Sandwiches", "imageUrl": "", "active": True},
        {"name": "Papas Cajun Grande", "description": "Papas fritas sazonadas estilo cajún", "price": 12.90, "category": "Sides", "imageUrl": "", "active": True},
        {"name": "Mashed Potatoes", "description": "Puré de papa cremoso con gravy", "price": 10.90, "category": "Sides", "imageUrl": "", "active": True},
        {"name": "Biscuit", "description": "Pan de buttermilk recién horneado", "price": 5.90, "category": "Sides", "imageUrl": "", "active": True},
        {"name": "Coca-Cola 500ml", "description": "Gaseosa bien fría", "price": 7.50, "category": "Bebidas", "imageUrl": "", "active": True},
    ],
    "popeyes-barranco": [
        # Productos exclusivos de Barranco
        {"name": "Combo Artista Barranco", "description": "5 piezas + papas + bebida + postre (especial Barranco)", "price": 55.00, "category": "Combos", "imageUrl": "", "active": True},
        {"name": "Pollo con Ají Barranco", "description": "Pollo crispy con salsa de ají amarillo exclusivo", "price": 28.00, "category": "Pollos", "imageUrl": "", "active": True},
        {"name": "Café Popeyes", "description": "Café pasado exclusivo de Barranco", "price": 8.00, "category": "Bebidas", "imageUrl": "", "active": True},
        # Productos compartidos
        {"name": "Bucket 8 Piezas", "description": "8 piezas de pollo crispy sazonado", "price": 64.90, "category": "Buckets", "imageUrl": "", "active": True},
        {"name": "Spicy Chicken Sandwich", "description": "Sandwich de pollo picante", "price": 21.90, "category": "Sandwiches", "imageUrl": "", "active": True},
        {"name": "Papas Cajun Grande", "description": "Papas fritas sazonadas estilo cajún", "price": 12.90, "category": "Sides", "imageUrl": "", "active": True},
        {"name": "Apple Pie", "description": "Pie de manzana crujiente con canela", "price": 8.90, "category": "Postres", "imageUrl": "", "active": True},
        {"name": "Coca-Cola 500ml", "description": "Gaseosa bien fría", "price": 7.50, "category": "Bebidas", "imageUrl": "", "active": True},
    ],
}
