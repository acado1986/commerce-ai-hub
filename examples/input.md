i have this spanish requierment Se plantea la migración y refactorización de la funcionalidad actualmente implementada en los módulos Vass_BestSellers y Vass_BestSellersFilter, con el objetivo de integrarla en una única solución basada en App Builder.
Como parte de esta PBI se abordarán las siguientes líneas de trabajo:
Unificación de módulos:
Consolidación de la lógica actualmente distribuida en ambos módulos en una única app de App Builder, simplificando la estructura de código, eliminando duplicidades y mejorando la mantenibilidad.
Adaptación a App Builder:
Reimplementación de la lógica existente para su correcto funcionamiento dentro del modelo serverless de App Builder, incluyendo la gestión de acciones, configuración, dependencias y despliegue.
Ejecución programada (cron):
Implementación de la capacidad de ejecutar procesos de forma programada (cron), lo que implica adaptar la lógica para su ejecución asíncrona y gestionar correctamente la recurrencia y posibles errores.
Revisión y optimización de lógica:
Análisis del comportamiento actual para detectar posibles mejoras, optimizar consultas y asegurar que el rendimiento es adecuado en el nuevo entorno.
Testing y validación:
Verificación funcional completa de la nueva implementación, asegurando que el comportamiento es equivalente o superior al actual.
El objetivo final es disponer de una solución más modular, escalable y alineada con la arquitectura objetivo, reduciendo la complejidad técnica y facilitando futuras evoluciones.
Adobe Commerce
Desglose de tareas:
Análisis inicial de los módulos actuales y su lógica.
Diseño de la nueva solución en App Builder.
Unificación y refactorización del código en una única app.
Implementación y adaptación al modelo serverless.
Implementación de ejecuciones programadas (cron).
Validación y pruebas para asegurar el correcto funcionamiento.  and i want to migrate to to APP BUILDER this 2 modules this is how this modules works. I want all the doc in english ## 1. Current Functionality Overview

### 1.1 Vass_BestSellers

Business purpose:
- Maintain and expose a list of “best seller” products based on recent order history.
- Optionally assign these products automatically to a specific Magento category for use in navigation/landing pages.
- Provide a backend button to trigger the process manually and an API endpoint to fetch the current best-seller list.

Key behaviors:
- Reads configuration from `bestsellers/bestSellersConfiguration/*` (section `bestsellers`):
  - `enable`: whether the automatic list update is active.
  - `url_key_category`: URL key of the category that will host the best-seller listing.
  - `dias_consulta`: number of days to look back for order data.
  - `maximo_productos`: max number of products to include.
  - `excepciones`: SKUs to exclude from the best-seller calculation.
- Backend system configuration UI under Stores → Configuration → Vass → Best sellers:
  - Defined in `app/code/Vass/BestSellers/etc/adminhtml/system.xml`.
  - Section id: `bestsellers`.
  - Group id: `bestSellersConfiguration`.
  - Also includes a backend button `btn_ejecutar` that calls an admin route.
- Admin route and manual trigger button:
  - `etc/adminhtml/routes.xml` defines router `bestsellers` (frontName `bestsellers`).
  - The system config button posts to `bestsellers/proceso/ejecutar`.
  - This is implemented by `Vass\BestSellers\Controller\Adminhtml\Proceso\Ejecutar`.
- API endpoint:
  - `etc/webapi.xml` exposes:
    - Method: `GET /V1/products-bestseller`.
    - Service: `Vass\BestSellers\Api\BestsellerInterface::getBestseller`.
  - DI preference in `etc/di.xml` maps the interface to `Vass\BestSellers\Model\Bestseller`.
- Frontend route:
  - `etc/frontend/routes.xml` registers frontName `bestsellers`, though there are no explicit frontend controllers in this module.

### 1.2 Vass_BestSellersFilter

Business purpose:
- Periodically compute sales-based metrics for all products and store them in custom attributes:
  - `bestsellers_qty_no_order`: total quantity sold in the configured window.
  - `bestsellers_qty`: global rank index for each product.
- Provide a configurable cron frequency and control over which SKUs to exclude.

Key behaviors:
- Configuration section `bestsellers_filter` (Stores → Configuration → Vass → Bestsellers Filter), defined in `etc/adminhtml/system.xml`:
  - Group `general`:
    - `enabled` (`bestsellers_filter/general/enabled`): master enable flag.
  - Group `filter_settings`:
    - `days_to_consult` (`bestsellers_filter/filter_settings/days_to_consult`): days window for order analysis.
    - `exceptions` (`bestsellers_filter/filter_settings/exceptions`): comma-separated list of SKUs to exclude.
  - Group `cron_settings`:
    - `frequency` (`bestsellers_filter/cron_settings/frequency`): cron expression used by the job.
- Cron configuration:
  - `etc/crontab.xml`:
    - Group id: `bestsellers_filter`.
    - Job name: `vass_bestsellers_filter`.
    - Instance: `Vass\BestSellersFilter\Cron\BestSellersFilter::execute`.
    - `config_path`: `bestsellers_filter/cron_settings/frequency`.
  - `etc/cron_groups.xml` defines the cron group behavior:
    - `schedule_generate_every`, `schedule_ahead_for`, `schedule_lifetime`, `history_*` and `use_separate_process`.
- Helper `Vass\BestSellersFilter\Helper\Settings` wraps configuration access:
  - `getModuleEnable()` → `bestsellers_filter/general/enabled`.
  - `getDaysToConsult()` → `bestsellers_filter/filter_settings/days_to_consult`.
  - `getCronSettingsFrequency()` → `bestsellers_filter/cron_settings/frequency`.
  - `getSkuExceptions()` → `bestsellers_filter/filter_settings/exceptions`.

## 2. How Vass_BestSellers Works Today

### 2.1 Configuration and Backend UI

- System config section `bestsellers` (file: `etc/adminhtml/system.xml`):
  - Path examples:
    - `bestsellers/bestSellersConfiguration/enable`.
    - `bestsellers/bestSellersConfiguration/url_key_category`.
    - `bestsellers/bestSellersConfiguration/dias_consulta`.
    - `bestsellers/bestSellersConfiguration/maximo_productos`.
    - `bestsellers/bestSellersConfiguration/excepciones`.
  - Provides a button field `btn_ejecutar` using frontend model `Vass\BestSellers\Block\Adminhtml\System\Config\Button` with label “Ejecutar Proceso Manualmente!” pointing to `bestsellers/proceso/ejecutar`.
- Default config values (`etc/config.xml`):
  - `vass/bestSellersConfiguration/enable = 1`.
  - `vass/bestSellersConfiguration/url_key_category = bestselling`.
  - `vass/bestSellersConfiguration/dias_consulta = 30`.
  - `vass/bestSellersConfiguration/maximo_productos = 15`.
  - `vass/bestSellersConfiguration/position_productos_manual = 1` (currently not used in the active code path).

### 2.2 Best-seller Calculation Logic

Core logic in `Vass\BestSellers\Helper\Helper` (`Helper/Helper.php`):

1. Date range calculation (`getFechasConsulta`):
   - Reads `dias_consulta` from config via `getConfigValores('dias_consulta')`.
   - Computes:
     - `fecha_to` = current date (`Y-m-d`).
     - `fecha_from` = `fecha_to` minus `dias_consulta` days.

2. Best-seller aggregation (`getBestSellingProducts`):
   - Reads exclusions with `getListadoExcepciones()` which reads `excepciones` from config, strips spaces, and splits by comma into an array of SKUs.
   - Uses an `OrderCollection` connection to construct a custom SQL select over:
     - `sales_order` table (alias `order`).
     - `sales_order_item` table (alias `order_item`).
   - Filters:
     - `order.status = 'complete'`.
     - `order.created_at` between `fecha_from 00:00:00` and `fecha_to 23:59:59`.
   - Groups by `order_item.product_id` and sums `qty_ordered`.
   - For each item:
     - Starts with `product_id`, `sku` and aggregated `qty_ordered`.
     - Uses `Configurable::getParentIdsByChild($productId)` to see if the product belongs to a configurable.
     - If a parent exists, loads the parent product via `ProductRepository` and replaces `sku` and ID with the parent values.
     - If resulting `sku` is not in the exceptions list, it:
       - Adds `qty_ordered` to `listItems[$sku]` (sum per SKU).
       - Stores a mapping `productsIds[sku] = finalProductId` for later use when assigning to categories.
   - After iterating all items:
     - Sorts `listItems` in descending order by quantity (`arsort`).
     - Returns the associative array `sku => total_quantity_sold`.

3. Manual execution via admin controller (`Controller/Adminhtml/Proceso/Ejecutar`):
   - Entry point: `bestsellers/proceso/ejecutar`.
   - Execution steps:
     1. Resolve category ID:
        - `Helper::getCategoryIdByUrlKey()` loads the category with attribute `url_key = vass/bestSellersConfiguration/url_key_category`.
     2. Clear existing products from that category:
        - `Helper::deleteProductFromCategory($categoryId)` fetches the product collection for that category and calls `CategoryLinkRepository::deleteByIds($categoryId, $sku)` for each product.
     3. Calculate best-sellers:
        - Calls `Helper::getBestSellingProducts()`.
     4. If there are results:
        - Calls `Helper::assignProductsToCategory($productList, $categoryId)`.
        - Inside this method:
          - Applies the `maximo_productos` limit.
          - Resolves product IDs from stored `productsIds[sku]` using `ProductRepository` and builds an ordered list of product IDs.
          - Delegates to `assignOrderToCategory($positions, $categoryId)` which:
            - Builds `positionTotal[product_id] = index`.
            - Loads the category by ID, calls `setPostedProducts($positionTotal)` and saves.
     5. Adds a success or notice message (with date range and item count) to the admin session.
     6. Redirects back to the referring URL.

4. API behavior (`Model/Bestseller`):
   - `Vass\BestSellers\Model\Bestseller::getBestseller()`:
     - Calls `Helper::getBestSellingProducts()`.
     - Calls `Helper::assignProducts($listProducts)` which:
       - Applies the `maximo_productos` limit.
       - Returns an array `[ ['sku' => 'SKU1'], ['sku' => 'SKU2'], ... ]`.
     - Returns `['data' => $rsAssign]`.
   - This is what `/V1/products-bestseller` returns.

### 2.3 Implicit Assumptions and Dependencies

- Orders considered:
  - Only orders with status exactly `'complete'` are included.
- Time window:
  - Relative to current date/time; not parameterized externally.
- Stock handling:
  - Not explicitly considered in `Vass_BestSellers` (only order quantity).
- Category behavior:
  - Category is fully cleared before re-assignment on each run.
- Dependencies on Magento modules:
  - `Magento_Sales`, `Magento_Catalog`, `Magento_ConfigurableProduct`, `Magento_Config`, `Magento_Backend`.
- Custom attributes:
  - This module does not directly introduce new product attributes; it relies on category assignments and API output.

## 3. How Vass_BestSellersFilter Works Today

### 3.1 Configuration and Cron

- System config section `bestsellers_filter` (file: `etc/adminhtml/system.xml`):
  - Paths:
    - `bestsellers_filter/general/enabled`.
    - `bestsellers_filter/filter_settings/days_to_consult`.
    - `bestsellers_filter/filter_settings/exceptions`.
    - `bestsellers_filter/cron_settings/frequency`.
- Cron job:
  - Group `bestsellers_filter` in `etc/crontab.xml`.
  - Job `vass_bestsellers_filter` bound to `Vass\BestSellersFilter\Cron\BestSellersFilter::execute`.
  - Cron expression read from config path `bestsellers_filter/cron_settings/frequency`.
- Cron group behavior (`etc/cron_groups.xml`):
  - Separate process (`use_separate_process=1`), custom schedule and history settings.

### 3.2 Execution Flow (`Cron/BestSellersFilter.php`)

1. `execute()`
   - Checks `Settings::getModuleEnable()` (config `bestsellers_filter/general/enabled`).
   - If disabled, returns early.
   - Otherwise, runs in order:
     1. `bestsellerQtyNoOrderToZero()`.
     2. `getProductsInOrders()`.
     3. `createIndex()`.

2. `bestsellerQtyNoOrderToZero()`
   - Loads a full product collection via `ProductCollectionFactory`.
   - Gets all product IDs.
   - If there are IDs, calls `ProductAction::updateAttributes` once with:
     - `bestsellers_qty_no_order = 0`.
     - `bestsellers_qty = 0`.
     - Scope `0` (admin/global).
   - If there are no products, logs an info message.

3. `getProductsInOrders()`
   - Builds date range with `getDateQuery()`:
     - Reads `days_to_consult` from `Settings::getDaysToConsult()`.
     - Computes `[date_from, date_to]` similarly to `Vass_BestSellers`.
   - Builds SKU exclusion list with `getSkuExceptionsList()` from config `bestsellers_filter/filter_settings/exceptions`.
   - Uses `OrderItemCollectionFactory` to get an order item collection and then manipulates its `Select`:
     - Joins:
       - `sales_order` (alias `so`) to filter by date range and status.
       - `cataloginventory_stock_item` (alias `csi`) to get `is_in_stock` and stock quantity.
       - `catalog_product_super_link` (alias `cpsl`) to get `super_parent_id` (configurable parent ID).
       - `catalog_product_entity` (alias `cpe`) to ensure the product exists.
     - Filters:
       - Orders where `so.created_at` is within `[date_from 00:00:00, date_to 23:59:59]` (if date range is set).
       - SKUs not in the exceptions list.
       - `so.status = 'complete'`.
       - `main_table.parent_item_id IS NULL` to avoid counting child rows twice.
     - Adds a `total_qty_sold` column as `SUM(qty_ordered)` (using `Zend_Db_Expr`).
     - Groups by `main_table.sku` and orders by `total_qty_sold DESC`.
   - Iterates over the resulting order items:
     - For each row:
       - Reads `product_id`, `total_qty_sold`, and `super_parent_id` (if exists).
       - If there is a `super_parent_id`, accumulates quantities in `$parentQtySold[parentId]`.
       - Updates attribute `bestsellers_qty_no_order` for the product (`product_id`) with its `total_qty_sold` using `ProductAction::updateAttributes` (per product).
   - After the loop, iterates over `$parentQtySold` and updates `bestsellers_qty_no_order` also for each parent configurable product.
   - On exception, prints an error message with `echo` (non-ideal for cron).

4. `createIndex()`
   - Loads a product collection via `ProductCollectionFactory`.
   - Adds attribute selections:
     - `bestsellers_qty_no_order`.
     - `bestsellers_qty`.
     - `name`.
   - Joins stock and status data:
     - `cataloginventory_stock_item` (`is_in_stock` via `joinField`).
     - `catalog_product_entity_int` + `eav_attribute` to get `status`.
   - Applies ordering:
     - `status ASC`.
     - `is_in_stock DESC`.
     - `CAST(bestsellers_qty_no_order AS UNSIGNED) DESC`.
     - `name ASC`.
   - Loads the collection.
   - Iterates over products, assigning an incremental index starting at 1:
     - For each product, calls `ProductAction::updateAttributes` to set:
       - `bestsellers_qty` = current index.
   - Logs any exceptions.

### 3.3 Dependencies and Assumptions

- Requires that the custom product attributes `bestsellers_qty_no_order` and `bestsellers_qty` exist and are usable in collections and updates.
- Assumes:
  - Orders with status `'complete'` represent completed sales.
  - A fixed stock (stock_id=1) via join in `createIndex`.
  - Product entity type id = 4 for fetching `status` attribute in the join.
- Depends on Magento modules: `Magento_Sales`, `Magento_Catalog`, `Magento_Cron`, `Magento_ConfigurableProduct`, `Magento_Inventory`/`CatalogInventory`.

## 4. Combined Behavior and Current Consumers

Together, the two modules provide:
- A best-seller list API (`/V1/products-bestseller`) returning a small, limited list of SKUs ordered by recent sales.
- A mechanism to populate a specific category with the top N best-seller products.
- A global best-seller index (`bestsellers_qty` and `bestsellers_qty_no_order`) for all products, updated on a schedule.

Likely consumers (to be confirmed):
- Frontend components or widgets using:
  - The best-seller category to display a “Best Sellers” shelf/page.
  - The `bestsellers_qty` attribute in sort orders or filtered collections.
- External integrations possibly querying `/V1/products-bestseller` to retrieve a curated list of top sellers.

## 5. Migration Plan to App Builder (High-Level)

The goal is to implement all this behavior in a single App Builder app, using Adobe Commerce APIs instead of direct DB/EAV access, and providing both scheduled and on-demand execution.

### 5.1 App Builder Components

1. **Action: `calculate-bestsellers`**
   - Inputs:
     - `days_to_consult` (from app config; equivalent to Magento configs).
     - `exceptions` (SKU list from app config).
   - Behavior:
     - Uses Commerce REST/GraphQL APIs (or a thin custom endpoint in Commerce) to fetch orders with status `complete` between `date_from` and `date_to`.
     - Aggregates quantities per product SKU, applying logic similar to `Helper::getBestSellingProducts` and `BestSellersFilter::getProductsInOrders`:
       - Ignore child rows (`parent_item_id` equivalent).
       - Resolve configurable parents.
       - Apply SKU exclusions.
     - Returns a list of objects:
       - `{ sku, qty_sold, parent_sku? }` sorted by `qty_sold` desc.

2. **Action: `update-product-index`**
   - Inputs:
     - List from `calculate-bestsellers`.
     - Configuration: batch size, flags for resetting existing index.
   - Behavior:
     - Option A (closest to current behavior):
       - Reset `bestsellers_qty_no_order` and `bestsellers_qty` for all products via Commerce APIs in batches.
     - Option B (optimization):
       - Only update products that appear in the current calculation, plus a tail/threshold.
     - Fetch products via Commerce APIs, get status and stock information.
     - Compute ranking order using similar criteria: enabled, in stock, qty_sold, name.
     - For each product, call Commerce APIs to update custom attributes:
       - `bestsellers_qty_no_order` = `qty_sold`.
       - `bestsellers_qty` = rank index.
     - Operate in batches and handle API rate limits and timeouts.

3. **Action: `assign-category-bestsellers`**
   - Inputs:
     - Best-seller list from `calculate-bestsellers`.
     - `maximo_productos`.
     - Category identifier (by ID or URL key) from app config.
   - Behavior:
     - Resolve category via Commerce category API.
     - Optionally clear existing product assignments (to mimic `deleteProductFromCategory`).
     - Take top `maximo_productos` SKUs.
     - Resolve product IDs via product API.
     - Update category product assignments and positions through Commerce APIs.
     - Return a summary: number of products assigned, date range used.

4. **Action: `orchestrate-bestsellers-cron`**
   - Orchestrates the entire flow:
     1. Read configuration from App Builder config/secrets (env vars): enable flag, days, exceptions, max products, category.
     2. Call `calculate-bestsellers`.
     3. Call `update-product-index`.
     4. Call `assign-category-bestsellers` (if enabled).
     5. Log a structured summary (counts, timings, errors).
   - Exposed:
     - As a scheduled action (App Builder scheduler → equivalent of Magento cron).
     - Optionally as an HTTP endpoint for manual triggering (replacement for the backend button and for `/V1/products-bestseller` for external consumers).

### 5.2 Configuration Mapping

Map Magento config to App Builder config/secrets:

- From `Vass_BestSellers`:
  - `bestsellers/bestSellersConfiguration/enable` → `BESTSELLERS_CATEGORY_ASSIGN_ENABLE`.
  - `bestsellers/bestSellersConfiguration/url_key_category` → `BESTSELLERS_CATEGORY_URL_KEY`.
  - `bestsellers/bestSellersConfiguration/dias_consulta` → `BESTSELLERS_DAYS_TO_CONSULT`.
  - `bestsellers/bestSellersConfiguration/maximo_productos` → `BESTSELLERS_MAX_PRODUCTS`.
  - `bestsellers/bestSellersConfiguration/excepciones` → `BESTSELLERS_EXCLUDED_SKUS`.
- From `Vass_BestSellersFilter`:
  - `bestsellers_filter/general/enabled` → `BESTSELLERS_INDEX_ENABLE`.
  - `bestsellers_filter/filter_settings/days_to_consult` → reuse `BESTSELLERS_DAYS_TO_CONSULT` or keep separate if needed.
  - `bestsellers_filter/filter_settings/exceptions` → unify with `BESTSELLERS_EXCLUDED_SKUS`.
  - `bestsellers_filter/cron_settings/frequency` → App Builder scheduler expression.

Store Commerce credentials as secrets:
- `COMMERCE_BASE_URL`.
- `COMMERCE_ADMIN_API_TOKEN` or equivalent.

### 5.3 Error Handling and Observability

Improvements over current implementation:
- Replace `echo`-based error reporting with structured logs and error responses.
- Ensure each action returns a JSON payload including:
  - `status` (success/partial_failure/failure).
  - `summary` (human-readable text).
  - `details` (array of errors, batch stats, etc.).
- Use App Builder logging facilities for:
  - Number of orders processed.
  - Number of products updated and skipped.
  - Execution time per step.

### 5.4 Performance and Scalability

- Use pagination and batch updates for:
  - Fetching orders.
  - Fetching products.
  - Updating attributes and category assignments.
- Design actions to respect serverless time limits:
  - If needed, separate the flow into multiple scheduled runs (e.g. per website or per product segment).
- Make the process idempotent:
  - Re-running for the same time window should overwrite previous values, not duplicate effects.

## 6. Open Points to Confirm Before Migration

- Exact consumers of `bestsellers_qty` and `bestsellers_qty_no_order` in the frontend and any 3rd-party integrations.
- Any business rules not visible in the code (e.g. specific store views, websites or customer groups to consider).
- Required latency/freshness for the best-seller data (e.g. daily, hourly).
- Whether manual execution (backoffice button) is still required, and from where it will be triggered post-migration.

This document, together with `01-analisis-actual.md`, `02-diseno-app-builder.md` and `03-plan-implementacion.md`, provides a full view of how the current modules behave and how their responsibilities will be implemented in Adobe App Builder.