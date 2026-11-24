# ============================================================
# SIGA · Punto Constructor (ferretería) · Programación 2
# Aplicación web con Streamlit sobre la base de datos SQLite
# ============================================================
import sqlite3
import threading
from datetime import date

import pandas as pd
import streamlit as st

st.set_page_config(page_title="SIGA · Punto Constructor", page_icon="🔧", layout="wide")

# ------------------------------------------------------------
# 1. CONEXIÓN Y CREACIÓN DE LA BASE (solo si no existe)
# ------------------------------------------------------------
@st.cache_resource
def conectar():
    """Crea una sola conexión que se reutiliza entre ejecuciones de la app."""
    con = sqlite3.connect("punto_constructor.db", check_same_thread=False)
    con.execute("PRAGMA foreign_keys = ON")
    return con


def crear_base(con):
    """Crea tablas, vista y datos de prueba solo si todavía no existen."""
    cur = con.cursor()
    cur.executescript("""
    CREATE TABLE IF NOT EXISTS proveedores (
        id_proveedor INTEGER PRIMARY KEY AUTOINCREMENT,
        nombre TEXT NOT NULL,
        telefono TEXT
    );

    CREATE TABLE IF NOT EXISTS clientes (
        id_cliente INTEGER PRIMARY KEY AUTOINCREMENT,
        nombre TEXT NOT NULL,
        telefono TEXT
    );

    CREATE TABLE IF NOT EXISTS productos (
        id_producto INTEGER PRIMARY KEY AUTOINCREMENT,
        nombre TEXT NOT NULL,
        categoria TEXT NOT NULL,
        unidad_medida TEXT NOT NULL,
        precio_unitario REAL NOT NULL,
        stock_minimo INTEGER NOT NULL DEFAULT 0
    );

    CREATE TABLE IF NOT EXISTS movimientos (
        id_movimiento INTEGER PRIMARY KEY AUTOINCREMENT,
        id_producto INTEGER NOT NULL,
        tipo TEXT NOT NULL CHECK (tipo IN ('entrada', 'salida')),
        motivo TEXT NOT NULL CHECK (motivo IN (
            'compra', 'venta', 'devolucion_proveedor',
            'ajuste_faltante', 'producto_danado')),
        cantidad INTEGER NOT NULL CHECK (cantidad > 0),
        fecha TEXT NOT NULL,
        id_proveedor INTEGER,
        id_cliente INTEGER,
        FOREIGN KEY (id_producto) REFERENCES productos(id_producto),
        FOREIGN KEY (id_proveedor) REFERENCES proveedores(id_proveedor),
        FOREIGN KEY (id_cliente) REFERENCES clientes(id_cliente)
    );

    CREATE VIEW IF NOT EXISTS vw_inventario_actual AS
    SELECT p.id_producto, p.nombre, p.categoria, p.unidad_medida, p.stock_minimo,
           COALESCE(SUM(CASE WHEN m.tipo = 'entrada' THEN m.cantidad ELSE -m.cantidad END), 0) AS stock
    FROM productos p
    LEFT JOIN movimientos m ON m.id_producto = p.id_producto
    GROUP BY p.id_producto, p.nombre, p.categoria, p.unidad_medida, p.stock_minimo;
    """)
    con.commit()

    # Datos de prueba: solo si la base está vacía
    if cur.execute("SELECT COUNT(*) FROM productos").fetchone()[0] == 0:
        cur.executemany(
            "INSERT INTO proveedores (nombre, telefono) VALUES (?, ?)",
            [
                ("Losada Muñoz SAS Central Mayorista de Materiales para la Construcción", "3101000001"),
                ("Ferretería Suprema", "3101000002"),
                ("Ferreplasticos Cali SAS", "3101000003"),
                ("Ferretería Bervar", "3101000004"),
            ],
        )
        cur.executemany(
            "INSERT INTO clientes (nombre, telefono) VALUES (?, ?)",
            [
                ("Ferretería El Tornillo (minorista)", "3201000001"),
                ("Carlos Mejía (albañil)", "3201000002"),
                ("Constructora Andina SAS (contratista)", "3201000003"),
                ("Luis Ramírez (electricista)", "3201000004"),
                ("Jorge Castillo (fontanero)", "3201000005"),
            ],
        )
        cur.executemany(
            """INSERT INTO productos (nombre, categoria, unidad_medida, precio_unitario, stock_minimo)
               VALUES (?, ?, ?, ?, ?)""",
            [
                ("Tubo PVC", "Plomería", "metro", 8500, 50),
                ("Martillo", "Herramientas", "unidad", 28000, 5),
                ("Manguera", "Plomería", "metro", 4200, 40),
                ("Cemento", "Materiales de construcción", "bulto", 32000, 20),
                ("Arena", "Materiales de construcción", "bulto", 9000, 30),
                ("Pintura", "Acabados", "galón", 65000, 8),
            ],
        )
        # Entradas: compras a proveedores
        cur.executemany(
            """INSERT INTO movimientos (id_producto, tipo, motivo, cantidad, fecha, id_proveedor)
               VALUES (?, ?, ?, ?, ?, ?)""",
            [
                (1, "entrada", "compra", 200, "2026-09-01", 3),
                (2, "entrada", "compra", 30,  "2026-09-01", 2),
                (3, "entrada", "compra", 150, "2026-09-01", 3),
                (4, "entrada", "compra", 100, "2026-09-02", 1),
                (5, "entrada", "compra", 120, "2026-09-02", 1),
                (6, "entrada", "compra", 40,  "2026-09-03", 4),
            ],
        )
        # Salidas: ventas a clientes
        cur.executemany(
            """INSERT INTO movimientos (id_producto, tipo, motivo, cantidad, fecha, id_cliente)
               VALUES (?, ?, ?, ?, ?, ?)""",
            [
                (4, "salida", "venta", 25, "2026-09-10", 2),
                (1, "salida", "venta", 60, "2026-09-11", 5),
                (6, "salida", "venta", 10, "2026-09-12", 3),
                (2, "salida", "venta", 6,  "2026-09-14", 1),
            ],
        )
        # Salida: devolución de mercancía a proveedor
        cur.execute(
            """INSERT INTO movimientos (id_producto, tipo, motivo, cantidad, fecha, id_proveedor)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (3, "salida", "devolucion_proveedor", 10, "2026-09-15", 3),
        )
        # Salidas sin tercero: faltante de inventario y producto dañado
        cur.executemany(
            """INSERT INTO movimientos (id_producto, tipo, motivo, cantidad, fecha)
               VALUES (?, ?, ?, ?, ?)""",
            [
                (5, "salida", "ajuste_faltante", 4, "2026-09-18"),
                (6, "salida", "producto_danado", 2, "2026-09-20"),
            ],
        )
        con.commit()


@st.cache_resource
def obtener_candado():
    """Un candado compartido: evita que dos sesiones creen la base a la vez."""
    return threading.Lock()


conexion = conectar()
with obtener_candado():
    crear_base(conexion)
cursor = conexion.cursor()

# ------------------------------------------------------------
# 2. FUNCIONES DEL AVANCE 4 (iguales a las del notebook)
# ------------------------------------------------------------
MOTIVOS_SALIDA = ("venta", "devolucion_proveedor", "ajuste_faltante", "producto_danado")
UNIDADES = ("metro", "unidad", "bulto", "galón")


def existe_producto(id_producto):
    cursor.execute("SELECT 1 FROM productos WHERE id_producto = ?", (id_producto,))
    return cursor.fetchone() is not None


def existe_proveedor(id_proveedor):
    cursor.execute("SELECT 1 FROM proveedores WHERE id_proveedor = ?", (id_proveedor,))
    return cursor.fetchone() is not None


def existe_cliente(id_cliente):
    cursor.execute("SELECT 1 FROM clientes WHERE id_cliente = ?", (id_cliente,))
    return cursor.fetchone() is not None


def cantidad_valida(cantidad):
    return isinstance(cantidad, int) and not isinstance(cantidad, bool) and cantidad > 0


def registrar_entrada(id_producto, cantidad, fecha=None, id_proveedor=None):
    fecha = fecha or date.today().isoformat()
    # 1. Validar
    if not cantidad_valida(cantidad):
        return False, "La cantidad debe ser un número entero mayor que 0."
    if not existe_producto(id_producto):
        return False, f"El producto {id_producto} no existe."
    if id_proveedor is not None and not existe_proveedor(id_proveedor):
        return False, f"El proveedor {id_proveedor} no existe."
    # 3 y 4. Ejecutar y confirmar (o deshacer)
    try:
        cursor.execute(
            """INSERT INTO movimientos (id_producto, tipo, motivo, cantidad, fecha, id_proveedor)
               VALUES (?, 'entrada', 'compra', ?, ?, ?)""",
            (id_producto, cantidad, fecha, id_proveedor))
        conexion.commit()
        return True, f"Entrada registrada: {cantidad} del producto {id_producto}."
    except Exception as e:
        conexion.rollback()
        return False, f"Error al guardar: {e}"


def registrar_salida(id_producto, cantidad, fecha=None, motivo="venta", id_cliente=None, id_proveedor=None):
    fecha = fecha or date.today().isoformat()
    # 1. Validar
    if not cantidad_valida(cantidad):
        return False, "La cantidad debe ser un número entero mayor que 0."
    if not existe_producto(id_producto):
        return False, f"El producto {id_producto} no existe."
    if motivo not in MOTIVOS_SALIDA:
        return False, f"Motivo inválido. Use uno de: {', '.join(MOTIVOS_SALIDA)}."
    if motivo == "venta" and (id_cliente is None or not existe_cliente(id_cliente)):
        return False, "Una venta necesita un cliente que exista."
    if motivo == "devolucion_proveedor" and (id_proveedor is None or not existe_proveedor(id_proveedor)):
        return False, "Una devolución necesita un proveedor que exista."
    # 2. Consultar el stock actual en la vista
    cursor.execute("SELECT stock FROM vw_inventario_actual WHERE id_producto = ?", (id_producto,))
    stock = cursor.fetchone()[0]
    if cantidad > stock:
        return False, f"Stock insuficiente: hay {stock} y se piden {cantidad}."
    # 3 y 4. Ejecutar y confirmar (o deshacer)
    try:
        cursor.execute(
            """INSERT INTO movimientos (id_producto, tipo, motivo, cantidad, fecha, id_proveedor, id_cliente)
               VALUES (?, 'salida', ?, ?, ?, ?, ?)""",
            (id_producto, motivo, cantidad, fecha, id_proveedor, id_cliente))
        conexion.commit()
        return True, f"Salida registrada ({motivo}): {cantidad} del producto {id_producto}."
    except Exception as e:
        conexion.rollback()
        return False, f"Error al guardar: {e}"


def consultar_inventario(categoria=None):
    if categoria:
        return pd.read_sql_query(
            "SELECT * FROM vw_inventario_actual WHERE categoria = ? ORDER BY nombre",
            conexion, params=(categoria,))
    return pd.read_sql_query("SELECT * FROM vw_inventario_actual ORDER BY nombre", conexion)


def alertas_stock_bajo(minimo=None):
    """Con 'minimo' compara contra ese número; sin él, contra el stock_minimo de cada producto."""
    if minimo is None:
        return pd.read_sql_query(
            "SELECT nombre, categoria, stock, stock_minimo FROM vw_inventario_actual "
            "WHERE stock < stock_minimo ORDER BY stock", conexion)
    return pd.read_sql_query(
        "SELECT nombre, categoria, stock, stock_minimo FROM vw_inventario_actual "
        "WHERE stock < ? ORDER BY stock", conexion, params=(minimo,))


def registrar_producto(nombre, categoria, unidad_medida, precio_unitario, stock_minimo=0):
    if not isinstance(nombre, str) or not nombre.strip():
        return False, "El nombre no puede estar vacío."
    if not isinstance(categoria, str) or not categoria.strip():
        return False, "La categoría no puede estar vacía."
    if unidad_medida not in UNIDADES:
        return False, f"Unidad inválida. Use una de: {', '.join(UNIDADES)}."
    if not isinstance(precio_unitario, (int, float)) or isinstance(precio_unitario, bool) or precio_unitario <= 0:
        return False, "El precio debe ser un número mayor que 0."
    if not isinstance(stock_minimo, int) or isinstance(stock_minimo, bool) or stock_minimo < 0:
        return False, "El stock mínimo debe ser un entero de 0 en adelante."
    try:
        cursor.execute(
            """INSERT INTO productos (nombre, categoria, unidad_medida, precio_unitario, stock_minimo)
               VALUES (?, ?, ?, ?, ?)""",
            (nombre.strip(), categoria.strip(), unidad_medida, precio_unitario, stock_minimo))
        conexion.commit()
        return True, f"Producto '{nombre.strip()}' creado con id {cursor.lastrowid}."
    except Exception as e:
        conexion.rollback()
        return False, f"Error al guardar: {e}"


def consultar_movimientos_proveedor(id_proveedor):
    return pd.read_sql_query(
        """SELECT pr.nombre AS proveedor, p.nombre AS producto, m.motivo, m.cantidad, m.fecha
           FROM movimientos m
           JOIN proveedores pr ON pr.id_proveedor = m.id_proveedor
           JOIN productos p ON p.id_producto = m.id_producto
           WHERE m.id_proveedor = ?
           ORDER BY m.fecha""", conexion, params=(id_proveedor,))


def registrar_entradas_lote(items, fecha=None, id_proveedor=None):
    """items = lista de pares (id_producto, cantidad)."""
    fecha = fecha or date.today().isoformat()
    try:
        if not items:
            raise ValueError("El lote está vacío.")
        if id_proveedor is not None and not existe_proveedor(id_proveedor):
            raise ValueError(f"El proveedor {id_proveedor} no existe.")
        for id_producto, cantidad in items:
            if not cantidad_valida(cantidad):
                raise ValueError(f"Cantidad inválida para el producto {id_producto}.")
            if not existe_producto(id_producto):
                raise ValueError(f"El producto {id_producto} no existe.")
            cursor.execute(
                """INSERT INTO movimientos (id_producto, tipo, motivo, cantidad, fecha, id_proveedor)
                   VALUES (?, 'entrada', 'compra', ?, ?, ?)""",
                (id_producto, cantidad, fecha, id_proveedor))
        conexion.commit()          # todo salió bien: confirmar
        return True, f"Lote registrado: {len(items)} entradas."
    except Exception as e:
        conexion.rollback()        # algo falló: deshacer TODO
        return False, f"Lote cancelado, no se guardó nada. Motivo: {e}"


# ------------------------------------------------------------
# 3. AYUDAS PARA LA INTERFAZ
# ------------------------------------------------------------
def leer_terceros(tabla, columna_id):
    """Devuelve un diccionario {nombre: id} de proveedores o clientes."""
    df = pd.read_sql_query(f"SELECT {columna_id}, nombre FROM {tabla} ORDER BY nombre", conexion)
    return dict(zip(df["nombre"], df[columna_id]))


def mostrar_mensaje_guardado():
    """Muestra (una sola vez) el mensaje que dejó el último registro."""
    guardado = st.session_state.pop("mensaje", None)
    if guardado:
        ok, texto = guardado
        if ok:
            st.success(texto)
        else:
            st.error(texto)


# ------------------------------------------------------------
# 4. PESTAÑAS
# ------------------------------------------------------------
def pestana_inicio():
    st.header("SIGA · Sistema de Inventario")
    st.write(
        "Sistema de control de inventario de **Punto Constructor**, una ferretería. "
        "Registra entradas (compras) y salidas (ventas, devoluciones, faltantes y daños), "
        "calcula el stock actual y avisa cuando un producto se está agotando."
    )
    inventario = consultar_inventario()
    bajos = alertas_stock_bajo()
    col1, col2, col3 = st.columns(3)
    col1.metric("Productos", len(inventario))
    col2.metric("Unidades en stock", int(inventario["stock"].sum()))
    col3.metric("Productos con stock bajo", len(bajos))


def pestana_registrar():
    st.header("Registrar movimiento")
    mostrar_mensaje_guardado()

    inv = consultar_inventario()
    productos = dict(zip(inv["nombre"], inv["id_producto"]))
    proveedores = leer_terceros("proveedores", "id_proveedor")
    clientes = leer_terceros("clientes", "id_cliente")
    sin_tercero = "(ninguno)"

    with st.form("form_movimiento"):
        nombre_producto = st.selectbox("Producto", list(productos.keys()))
        tipo = st.selectbox("Tipo de movimiento", ["entrada", "salida"])
        cantidad = st.number_input("Cantidad", min_value=1, value=1, step=1)
        st.caption("Solo para salidas: motivo y, según el motivo, cliente (venta) o proveedor (devolución).")
        motivo = st.selectbox("Motivo de la salida", list(MOTIVOS_SALIDA))
        nombre_cliente = st.selectbox("Cliente (ventas)", [sin_tercero] + list(clientes.keys()))
        nombre_proveedor = st.selectbox(
            "Proveedor (compras y devoluciones)", [sin_tercero] + list(proveedores.keys()))
        enviado = st.form_submit_button("Registrar")

    if enviado:
        id_producto = int(productos[nombre_producto])
        id_cliente = None if nombre_cliente == sin_tercero else int(clientes[nombre_cliente])
        id_proveedor = None if nombre_proveedor == sin_tercero else int(proveedores[nombre_proveedor])
        if tipo == "entrada":
            resultado = registrar_entrada(id_producto, int(cantidad), id_proveedor=id_proveedor)
        else:
            resultado = registrar_salida(
                id_producto, int(cantidad), motivo=motivo,
                id_cliente=id_cliente, id_proveedor=id_proveedor)
        # Se guarda el mensaje y se recarga la app para actualizar todos los datos
        st.session_state["mensaje"] = resultado
        st.rerun()


def pestana_inventario():
    st.header("Inventario actual")
    inventario = consultar_inventario()
    categorias = ["Todas"] + sorted(inventario["categoria"].unique())
    categoria = st.selectbox("Filtrar por categoría", categorias)
    if categoria == "Todas":
        tabla = consultar_inventario()
    else:
        tabla = consultar_inventario(categoria)
    st.dataframe(tabla, width="stretch", hide_index=True)


def pestana_alertas():
    st.header("Alertas de stock bajo")
    minimo = st.slider("Stock mínimo", min_value=0, max_value=300, value=50, step=5)
    bajos = alertas_stock_bajo(minimo)
    if bajos.empty:
        st.info(f"Ningún producto tiene menos de {minimo} unidades.")
    else:
        st.warning(f"{len(bajos)} producto(s) con menos de {minimo} unidades.")
        st.dataframe(bajos, width="stretch", hide_index=True)
        st.bar_chart(bajos.set_index("nombre")["stock"])


# ------------------------------------------------------------
# 5. PROGRAMA PRINCIPAL
# ------------------------------------------------------------
st.title("🔧 Punto Constructor")
tab1, tab2, tab3, tab4 = st.tabs(["Inicio", "Registrar movimiento", "Inventario", "Alertas"])
# Cada pestaña usa el candado para que dos sesiones no lean y escriban la base a la vez
with tab1:
    with obtener_candado():
        pestana_inicio()
with tab2:
    with obtener_candado():
        pestana_registrar()
with tab3:
    with obtener_candado():
        pestana_inventario()
with tab4:
    with obtener_candado():
        pestana_alertas()
