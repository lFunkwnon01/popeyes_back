from src.shared import config


# === 3 TIENDAS (sedes) ===
# Cada tienda tiene su propio admin + sus propios productos exclusivos.
# Algunas productos son compartidos entre tiendas (los "core" del menú).
SEED_STORES = [
    {
        "tenantId": config.DEFAULT_TENANT_ID,
        "storeId": "store-001",
        "name": "Popeyes Miraflores",
        "address": "Av. Larco 345, Miraflores, Lima",
        "active": True,
    },
    {
        "tenantId": config.DEFAULT_TENANT_ID,
        "storeId": "store-002",
        "name": "Popeyes Surco",
        "address": "Av. Caminos del Inca 1234, Surco, Lima",
        "active": True,
    },
    {
        "tenantId": config.DEFAULT_TENANT_ID,
        "storeId": "store-003",
        "name": "Popeyes Barranco",
        "address": "Jr. Bolognesi 567, Barranco, Lima",
        "active": True,
    },
]


# === USERS ===
# - 1 ADMIN por tienda (cada admin maneja SOLO su tienda)
# - 1 worker (RESTAURANT_WORKER, COOK, DISPATCHER, DELIVERY_DRIVER) por tienda
# - 1 CLIENT global (puede pedir en cualquier tienda)
SEED_USERS = [
    # Miraflores
    {"email": "admin.miraflores@popeyes.pe", "name": "Maria Admin Miraflores", "role": "ADMIN", "storeId": "store-001"},
    {"email": "worker.miraflores@popeyes.pe", "name": "Carlos Recepcionista", "role": "RESTAURANT_WORKER", "storeId": "store-001"},
    {"email": "cook.miraflores@popeyes.pe", "name": "Juan Cocinero", "role": "COOK", "storeId": "store-001"},
    {"email": "dispatcher.miraflores@popeyes.pe", "name": "Ana Empacadora", "role": "DISPATCHER", "storeId": "store-001"},
    {"email": "driver.miraflores@popeyes.pe", "name": "Luis Repartidor", "role": "DELIVERY_DRIVER", "storeId": "store-001"},
    # Surco
    {"email": "admin.surco@popeyes.pe", "name": "Roberto Admin Surco", "role": "ADMIN", "storeId": "store-002"},
    {"email": "worker.surco@popeyes.pe", "name": "Sofia Recepcionista", "role": "RESTAURANT_WORKER", "storeId": "store-002"},
    {"email": "cook.surco@popeyes.pe", "name": "Miguel Cocinero", "role": "COOK", "storeId": "store-002"},
    {"email": "dispatcher.surco@popeyes.pe", "name": "Patricia Empacadora", "role": "DISPATCHER", "storeId": "store-002"},
    {"email": "driver.surco@popeyes.pe", "name": "Andres Repartidor", "role": "DELIVERY_DRIVER", "storeId": "store-002"},
    # Barranco
    {"email": "admin.barranco@popeyes.pe", "name": "Elena Admin Barranco", "role": "ADMIN", "storeId": "store-003"},
    {"email": "worker.barranco@popeyes.pe", "name": "Diego Recepcionista", "role": "RESTAURANT_WORKER", "storeId": "store-003"},
    {"email": "cook.barranco@popeyes.pe", "name": "Lucia Cocinera", "role": "COOK", "storeId": "store-003"},
    {"email": "dispatcher.barranco@popeyes.pe", "name": "Fernando Empacador", "role": "DISPATCHER", "storeId": "store-003"},
    {"email": "driver.barranco@popeyes.pe", "name": "Carmen Repartidora", "role": "DELIVERY_DRIVER", "storeId": "store-003"},
    # Cliente global (puede pedir en cualquier tienda)
    {"email": "cliente@popeyes.pe", "name": "Cliente Popeyes", "role": "CLIENT", "storeId": ""},
]


# === PRODUCTOS POR TIENDA ===
# Estructura: { "store-001": [producto1, producto2, ...], "store-002": [...] }
# Cada producto tiene su storeId inyectado al guardarse.
SEED_PRODUCTS_BY_STORE = {
    "store-001": [
        # Productos exclusivos de Miraflores
        {"name": "Combo Familiar Miraflores", "description": "10 piezas + 2 papas grandes + 4 bebidas (especial Miraflores)", "price": 99.90, "category": "Combos", "imageUrl": "", "active": True},
        {"name": "Pollo a la Brasa Miraflores", "description": "Pollo a la brasa estilo peruano, exclusivo de esta sede", "price": 45.00, "category": "Pollos", "imageUrl": "", "active": True},
        # Productos compartidos (también en otras tiendas)
        {"name": "Bucket 8 Piezas", "description": "8 piezas de pollo crispy sazonado", "price": 64.90, "category": "Buckets", "imageUrl": "", "active": True},
        {"name": "Bucket 12 Piezas", "description": "12 piezas para compartir", "price": 89.90, "category": "Buckets", "imageUrl": "", "active": True},
        {"name": "Classic Chicken Sandwich", "description": "Pollo crispy, pepinillo y salsa mayo", "price": 19.90, "category": "Sandwiches", "imageUrl": "", "active": True},
        {"name": "Spicy Chicken Sandwich", "description": "Sandwich de pollo picante", "price": 21.90, "category": "Sandwiches", "imageUrl": "", "active": True},
        {"name": "Papas Cajun Grande", "description": "Papas fritas sazonadas estilo cajún", "price": 12.90, "category": "Sides", "imageUrl": "", "active": True},
        {"name": "Chicken Tenders (6 unid.)", "description": "Tiras de pollo empanizado crujiente", "price": 29.90, "category": "Pollos", "imageUrl": "", "active": True},
        {"name": "Coca-Cola 500ml", "description": "Gaseosa bien fría", "price": 7.50, "category": "Bebidas", "imageUrl": "", "active": True},
    ],
    "store-002": [
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
    "store-003": [
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


# === COMPATIBILIDAD: SEED_PRODUCTS y SEED_STORE legacy ===
# Mantenidos para no romper imports en otros archivos. Usar las nuevas
# constantes SEED_STORES y SEED_PRODUCTS_BY_STORE en el seed handler.
SEED_PRODUCTS = SEED_PRODUCTS_BY_STORE[config.DEFAULT_STORE_ID]
SEED_STORE = SEED_STORES[0]
