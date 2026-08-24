# Publicación en Streamlit Community Cloud

La aplicación está preparada para desplegarse sin secretos. Community Cloud requiere una sesión autenticada y autorización OAuth de GitHub; no ofrece un comando local para crear el deploy.

## Valores del formulario

| Campo | Valor |
|---|---|
| Repository | `salvamalfa/aeromexico-tracker` |
| Branch | `master` |
| Main file path | `streamlit_app.py` |
| App URL | `aeromexico-tracker`, si está disponible; de lo contrario aceptar el generado |
| Python version | **3.13** |
| Secrets | Ninguno |

## Pasos

1. Abrir [Streamlit Community Cloud](https://share.streamlit.io/) y continuar con GitHub.
2. Completar la autenticación y autorizar las aplicaciones OAuth que Streamlit usa para identidad y acceso al repositorio público.
3. Elegir **Create app** y después **Yup, I have an app**.
4. Capturar los valores de la tabla anterior.
5. Abrir **Advanced settings** y seleccionar Python **3.13**. El proyecto declara `>=3.13,<3.14`; el default 3.12 no es compatible.
6. Dejar Secrets vacío y pulsar **Deploy**.
7. Esperar a que termine la instalación y comprobar las diez páginas.
8. Sustituir en `README.md` el texto pendiente y el badge por la URL `streamlit.app` verificada.

## Verificación posterior

- Resumen abre en `2026Q2` y muestra seis tarjetas.
- `/forecast` abre directamente y muestra MAPE, sMAPE, backtest y bandas 80/95.
- Competencia muestra IFRS/US-GAAP, cierre fiscal de Ryanair y falta de stage length.
- Salud de datos muestra 23 issues y 66 restatements para el corte actual.
- El pie indica “proyecto independiente y no oficial” y “no es consejo de inversión”.
- No aparecen errores de dependencias, archivos Parquet o versión de Python en los logs.

Referencias oficiales: [crear el deploy](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/deploy), [crear la cuenta](https://docs.streamlit.io/deploy/streamlit-community-cloud/get-started/create-your-account) y [conectar GitHub](https://docs.streamlit.io/deploy/streamlit-community-cloud/get-started/connect-your-github-account).
