I have this description of a DevOps task. I need to extract the requirements for this task. I need to migrate this app from Adobe Commerce to App Builder / API Mesh.

 

Se plantea la migración del módulo Vass_SenseiCustom, actualmente encargado de gestionar el bypass de peticiones hacia Adobe Sensei a través de Adobe Commerce, con el objetivo de adaptarlo a la arquitectura basada en App Builder y API Mesh.

 

La migración implicará trasladar y adaptar la lógica existente a API Mesh, asegurando que las peticiones se enrutan correctamente hacia Sensei, manteniendo el comportamiento actual y garantizando la compatibilidad con el resto de servicios.

 

Además, se aprovechará la migración para revisar la implementación actual y asegurar que la solución queda alineada con una arquitectura más modular, escalable y mantenible.

 

Adobe Commerce
Desglose de tareas: 
Análisis del módulo actual y su lógica de bypass hacia Sensei.
Diseño de la solución en API Mesh para gestionar las peticiones.
Migración y adaptación de la lógica a la nueva arquitectura.
Configuración de rutas y endpoints en API Mesh.
Validación del comportamiento para asegurar equivalencia con la solución actual.
Testing e integración con los servicios consumidores.

 

The current module is located at:

 

/var/www/html/localdevrepsol/app/code/Vass/SenseiCustom

 

Can you confirm if you have access to this route: /home/bogdan/Projects/repsol-reward/app/code/Vass/SenseiCustom ?