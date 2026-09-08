# Publicación en Streamlit Community Cloud

Estado: **PUBLICADO Y VERIFICADO EL 2026-09-01**

URL pública: [aeromexico-tracker-djwjbylohwdryhbvnjhwsy.streamlit.app](https://aeromexico-tracker-djwjbylohwdryhbvnjhwsy.streamlit.app/)

La aplicación se desplegó sin secretos. Community Cloud requiere una sesión autenticada y autorización OAuth de GitHub; no ofrece un comando local para crear el deploy.

## Valores del formulario

| Campo | Valor |
|---|---|
| Repository | `salvamalfa/aeromexico-tracker` |
| Branch | `master` |
| Main file path | `streamlit_app.py` |
| App URL | `aeromexico-tracker-djwjbylohwdryhbvnjhwsy` |
| Python version | **3.13** |
| Secrets | Ninguno |

## Pasos

1. Abrir [Streamlit Community Cloud](https://share.streamlit.io/) y continuar con GitHub.
2. Completar la autenticación y autorizar las aplicaciones OAuth que Streamlit usa para identidad y acceso al repositorio público.
3. Elegir **Create app** y después **Yup, I have an app**.
4. Capturar los valores de la tabla anterior.
5. Abrir **Advanced settings** y seleccionar Python **3.13**. El proyecto declara `>=3.13,<3.14`; el default 3.12 no es compatible.
6. Dejar Secrets vacío y pulsar **Deploy**.
7. Esperar a que termine la instalación y comprobar Lectura ejecutiva, Economía unitaria y Vuelos.
8. Comprobar el selector trimestral, las gráficas y la navegación entre las tres pestañas.
9. Sustituir en `README.md` el texto pendiente y el badge por la URL `streamlit.app` verificada.

## Verificación posterior completada

- PASS — Lectura ejecutiva abre en `2T26` con el análisis aprobado.
- PASS — Economía unitaria muestra RASK, CASK, ASK y Margen unitario.
- PASS — Vuelos muestra Pasajeros, ASM, RPM y Ocupación, además de red y capacidad/demanda.
- PASS — El pie indica “proyecto independiente y no oficial” y “no es consejo de inversión”.
- PASS — Las tres vistas cargan sin errores y sin recursos externos.
- PASS — El documento no presenta desbordamiento horizontal a 360 px ni en escritorio.

El primer arranque detectó que las dependencias visuales estaban en un extra opcional que Community Cloud no instaló. Se movieron a dependencias principales y el despliegue quedó operativo en el commit `8ac5c97`.

Referencias oficiales: [crear el deploy](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/deploy), [crear la cuenta](https://docs.streamlit.io/deploy/streamlit-community-cloud/get-started/create-your-account) y [conectar GitHub](https://docs.streamlit.io/deploy/streamlit-community-cloud/get-started/connect-your-github-account).
