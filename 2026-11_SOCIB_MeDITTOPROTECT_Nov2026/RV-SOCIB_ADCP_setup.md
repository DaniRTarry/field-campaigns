# RV-SOCIB_ADCP_setup

## ADCP (PCLab4, NAS)

### 1. Adquisición — VmDas

Abrir **VmDas** → **Options** → **Edit Data Options**.

1. **Communications**: no tocar.
2. **File name**:
   - **Folder**: `2026-11_SOCIB_MeDITTOPROTECT_Nov2026`
   - **Number**: empezar en `1` e ir incrementando en cada nuevo registro. Por defecto VmDas propone el siguiente número, pero revisarlo siempre.
3. **ADCP Setup**:
   - **Bottom Track (BT)**: dejarlo **activado siempre** (también en el talud). Ver nota abajo.
   - Planificar los **bins** (número y tamaño).
4. **Recording** — comprobar antes de dejarlo corriendo:
   - **ADCP comms**: debe aparecer *pinging* → funcionando.
   - **NMEA comms**: debe aparecer *"… will be stored …"* → OK.

> [!WARNING]
> Si algo no funciona, cerrar VmDas y volver a abrirlo. Se generará un archivo nuevo con el número siguiente: **anotar que el archivo anterior es malo**.

> [!IMPORTANT]
> **Bottom Track: por qué dejarlo siempre activado**
> - Con fondo a menos de ~500 m, el eco del fondo contamina los bins más profundos. Sin BT no se puede saber dónde está el fondo, y esos bins pasan como datos buenos.
> - Con fondo más profundo, el BT no encuentra el fondo y no da datos, pero no estropea nada. Solo cuesta algunos pings de agua (algo más de ruido en cada promedio).
> - Para cambiarlo hay que parar y reiniciar VmDas. En el talud (de 200 a 1000 m en poco espacio) acabaría cortando secciones, y si se olvida reactivarlo al volver a la plataforma se pierde el control del fondo.
> - Solo desactivarlo en un tramo largo y continuo sobre fondo de **más de ~600 m**, en un cambio de rumbo o entre secciones. **Reactivarlo antes de volver a menos de ~500 m** y anotarlo.

### 2. Visualización — WinADCP

1. **Seleccionar el archivo `STA`**.
   - Si no se ve en la ventana (**Window**), deseleccionarlo y volver a seleccionarlo, tanto en **Whole** como en **Subset**.
2. **Monitor**: **Interval** = `120` s → **On**.
3. **Opciones de visualización**: **Options** → **Chart Options** → **Contour**.

### 3. Procesado — WinADCP

1. Para convertir los datos: abrir **WinADCP** → **Export**.
2. Antes de exportar, consultar el número de pings del archivo en **Chart Options** → **Contour**.
   - Si es **≤ 256**: no hay que hacer nada.
   - Si es **> 256**: apuntar el número (en papel o de memoria), porque hay que introducirlo en el paso siguiente.
3. **Series / Ancillary**:
   - **Ensemble**: si el archivo tiene más de 256 pings, introducir aquí el número apuntado en el paso anterior.
   - Revisar la configuración de Andrea (hoja en papel en el barco).
   - **Write File** en formato **TXT** y **MAT**.
4. Guardar en `SISTEMA/OCEANO/RDI/DATOS_CONVERTED/2026-11_SOCIB_MeDITTOPROTECT_Nov2026/`

> [!WARNING]
> Si el archivo tiene más de 256 pings y no se introduce el número en **Ensemble**, los datos exportados saldrán cortados.
