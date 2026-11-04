# Decisiones de chunking y de recuperación

Este documento responde a las dos preguntas de diseño del asistente de manuales. Los números son los que ejecuta el servicio. El código está en `backend/app/ingest/chunking.py`, `backend/app/retrieval/search.py`, `backend/app/core/config.py` y la revisión Alembic `0001_initial`. El registro corto de las mismas decisiones está en [DECISIONS.md](DECISIONS.md).

La primera vez que aparece un término, la explicación va entre paréntesis justo detrás. Cuando el término es un umbral, el paréntesis dice también si el valor buscado es el más bajo o el más alto.

## Chunking y dimensión del embedding

### Qué se eligió

Los manuales se parten primero por estructura (páginas impresas, encabezados o el fichero entero, antes de cortar el texto) y después se empaquetan en ventanas (trozos de longitud fija dentro de esa estructura). Cada ventana mide **800 caracteres** (letras y espacios, no tokens; un valor mayor mezcla varios hechos en la misma cita, un valor menor parte un rango de tensión por la mitad; 800 es el tamaño elegido, no un máximo que convenga subir) con **120 caracteres de solapamiento** (el final de una ventana se repite al principio de la siguiente; un solapamiento mayor duplica más texto y aporta menos texto nuevo, uno menor corta los hechos que caen en el borde; 120 es el solapamiento elegido). La dimensión del embedding (cuántos números tiene el vector que representa un texto; tiene que coincidir exactamente con el modelo y con la columna, ni más ni menos) es **384**. La columna es `vector(384)` (tipo de pgvector de anchura fija; un vector más largo no cabe y uno más corto no rellena la columna), con un índice HNSW (grafo de vecinos cercanos que acelera la búsqueda; no cambia el significado de la distancia) de distancia coseno (0 es idéntico y 2 es opuesto; una distancia más baja es un parecido mejor).

| Decisión | Valor | Por qué ese valor y no otro | Dónde vive |
| --- | --- | --- | --- |
| Tamaño de ventana | 800 caracteres (`CHUNK_SIZE`, mínimo 200) | Más alto mezcla especificaciones distintas en una cita. Más bajo parte una frase de alimentación. 800 cabe en una cita y varios caben en el prompt. | `config.py`, `chunk_pages` |
| Solapamiento | 120 caracteres (`CHUNK_OVERLAP`), cerca del 15 % | Más alto repite casi la misma ventana. Más bajo pierde el par de tensión que cae en el corte. No puede ser mayor o igual que el tamaño. | misma ventana, nunca la página siguiente |
| Unidad | caracteres, no tokens (trozos según el tokenizador de un modelo concreto) | Un tokenizador distinto movería los cortes. El mismo pasaje tiene que ser estable con el hash de tests, con `all-minilm` y con cualquier modelo de chat. | el corte no depende del modelo |
| PDF | un chunk (una ventana ya guardada, con su página y su vector) no cruza la página impresa | Si cruzara, la cita abriría una página que no contiene todo el texto. | el `page` de la cita es la página que el técnico abre |
| Markdown | cada encabezado abre una sección y ese índice se guarda como página | El Markdown no tiene página impresa. Sin este corte, todo el fichero sería una sola cita. | un `#` empieza sección |
| Texto plano | un solo bloque, página 1 | No hay encabezados que respetar. | |
| Embedding | 384 números | Es lo que devuelve `all-minilm` y lo que produce el hash de tests. 768 o 1536 no entran en la columna. | `all-minilm` en Docker; hash determinista en tests |

### Por qué primero la estructura

Una cita (el pasaje que el técnico puede abrir, con título y número de página) tiene que poder abrirse en el sitio correcto. Si un trozo mezclara el final de la página 3 y el principio de la página 4, el número guardado mentiría: el técnico abriría la 3 y no vería el hecho de la 4. Por eso el PDF se trocea página a página, después de leer cada página en orden de columnas (de arriba abajo en cada columna, y luego la columna de la derecha; el flujo plano de PyMuPDF mezcla las columnas y una frase de la derecha quedaría en medio de la izquierda). El Markdown no tiene página impresa, así que cada encabezado (`#`) empieza una sección y esa sección se numera como página. El texto plano es una sola página. El solapamiento no salta esa frontera: un hecho de la página 4 no aparece citado como página 3. Un solapamiento que cruzara páginas mejoraría un poco el recuerdo de un hecho a caballo entre dos páginas y empeoraría la honestidad de la cita. Se prefirió la cita honesta.

Una página vacía no produce chunk. Un fichero sin capa de texto (el texto que el PDF ya trae seleccionable; un escaneo es una foto y no la tiene) falla el trabajo. No hay OCR (reconocimiento de caracteres sobre una imagen). No se quiere indexar una página en blanco como si contuviera un procedimiento, porque la búsqueda devolvería esa página y el modelo podría inventar a partir de nada.

### Por qué 800 y 120

800 caracteres son un pasaje corto y citable, del orden de 120 a 200 tokens, y no una página entera de datasheet. Una página de ficha técnica puede tener varios miles de caracteres y mezclar alimentación, temperaturas y opciones. Si el chunk fuera la página entera, la cita sería demasiado larga y el modelo tendería a fundir varios números en uno. Si el chunk fuera una sola frase, un rango escrito en dos frases ("Power supply" en una línea y "9–32 V" en la siguiente) quedaría partido y la comparación numérica perdería el límite. 800 es el punto en el que cabe un hecho completo y todavía se pueden mandar varios chunks en el mismo prompt (el texto que se envía al modelo junto con la pregunta).

120 caracteres son aproximadamente el 15 % de la ventana. Un valor más alto, por ejemplo 400, haría que cada ventana nueva aportara solo la mitad de texto fresco y el índice guardaría el mismo párrafo muchas veces. Un valor más bajo, por ejemplo 0, cortaría un "9–32 V" que empiece en el carácter 790. 120 basta para repetir el final de la frase anterior. El corte busca un espacio en la segunda mitad de la ventana, así que no parte una palabra: cortar por la mitad de "NB-IoT" haría que ni la búsqueda por texto ni el embedding vieran el término entero. Si alguien configura un solapamiento mayor o igual que el tamaño, se reduce a un quinto del tamaño. Sin esa reducción la ventana siguiente empezaría en el mismo sitio o detrás, y el bucle no avanzaría. Un solapamiento mayor que el tamaño no es un ajuste válido.

No se trocea por tokens porque el mismo pasaje tiene que ser estable con el proveedor falso (el hash de tests, que no llama a ningún modelo), con `all-minilm` y con un modelo de chat distinto. El tokenizador cambiaría las fronteras cada vez que cambiara el modelo. No se trocea por frases sueltas porque una especificación de alimentación suele ocupar más de una frase y la cita quedaría cortada a la mitad del rango.

Cambiar `CHUNK_SIZE` no reescribe los manuales ya guardados. Los vectores describen el texto que ya está en la fila. Hace falta volver a ingestar, o borrar los chunks y reingestar, para que el nuevo tamaño exista en el índice. Un tamaño nuevo sin reingesta dejaría convivir ventanas de 800 con ventanas de otro tamaño, y la calibración de distancias dejaría de significar lo mismo.

### Por qué la columna es `vector(384)`

La columna se fijó en 384 porque la anchura tiene que ser la del modelo, no una anchura "cuanto más alta, mejor". Un vector más largo guarda más matices semánticos y también ocupa más índice, pero solo sirve si el modelo lo produce. Aquí coinciden tres restricciones:

1. `all-MiniLM-L6-v2`, que Ollama sirve como `all-minilm`, devuelve 384 valores. Es el embedder (el modelo que convierte texto en vector) real del despliegue Docker y cabe en la columna sin recorte ni relleno. Recortar un vector de 768 a 384 destruiría el significado de las posiciones. Rellenar con ceros un vector de 384 hasta 768 alejaría todas las distancias coseno de las que el modelo calculó.
2. El proveedor de tests hashea las palabras a un vector unitario (longitud 1, para que la distancia coseno no dependa de cuántas palabras había) de la misma anchura. Los tests y el índice comparten el tipo `vector(384)`. Si los tests usaran otra anchura, no podrían escribir en la misma columna.
3. Un índice HNSW de coseno sobre 384 es barato para una biblioteca de manuales de taller. No hace falta la anchura de un modelo de 768 o 1536 para citar un par de apriete que, además, se recupera por las palabras. Subir la anchura sin cambiar de modelo no añade información.

`nomic-embed-text` está disponible en Ollama y no se usa: devuelve 768 valores, que es más de lo que la columna acepta. `text-embedding-3-small` devuelve 1536 por defecto y este servicio no pide al proveedor una anchura menor. Pedir 384 a ese modelo sería otro modelo a efectos prácticos y exigiría la migración de más abajo. Al embeber, si el vector no mide exactamente `EMBEDDING_DIMENSION` (la anchura que el proceso cree que va a recibir; tiene que ser igual a la columna), la llamada falla. Al arrancar, si esa dimensión no coincide con `vector_dimension` (la anchura de la columna activa, hoy 384), el proceso se niega a usar ese proveedor. Así no se escribe un vector que la columna no puede guardar, ni se compara un vector de 384 con uno de 768: la distancia entre anchuras distintas no está definida.

Cada chunk guarda `embedding_model` (el nombre del modelo que produjo el vector; la búsqueda solo lee filas de ese nombre) y `embedding_dim` (la anchura con la que se calculó, para poder detectar una fila vieja). La búsqueda filtra por el nombre del modelo activo. Un chunk hasheado con `fake-hash-384` y un chunk de `openai/all-minilm` no entran en la misma consulta, aunque los dos midan 384. Mezclarlos haría que una distancia de 0,4 del hash y una distancia de 0,4 de MiniLM parecieran el mismo parecido, y no lo son. Por eso, al pasar el despliegue de hash a `all-minilm`, hubo que reembeber las filas: el contenido no cambió, cambiaron el nombre del modelo y los vectores.

El chat y los embeddings se eligen por separado. El chat puede ser Llama, GPT, Claude o Gemini. Cambiar el chat no cambia la columna. Los embeddings siguen en 384 mientras la columna no cambie.

### Cómo se migra si el modelo de embeddings cambia

Hay dos casos. El primero no toca el esquema (la forma de las tablas). El segundo sí.

**La nueva anchura sigue siendo 384.** Se cambia `EMBEDDING_MODEL` (el identificador LiteLLM del modelo de embeddings) y se llama a `reindex_embeddings` (vuelve a calcular el vector de las filas cuyo nombre de modelo ya no es el activo). Esa función las embebe en lotes de 16 (un lote mayor puede hacer fallar una sola petición a Ollama; uno menor solo añade viajes) y actualiza el vector, el nombre y `embedding_dim`. La búsqueda deja de ver los vectores viejos en cuanto el nombre deja de coincidir, así que el reindexado es el paso que vuelve a hacerlos visibles. No hace falta una revisión de Alembic (un cambio de esquema versionado). Es el camino usado al sustituir el hash por `all-minilm`. Un valor de dimensión distinto de 384 no puede usar este camino.

**La nueva anchura no es 384.** No se altera `vector(384)` in situ. pgvector no guarda un vector de otra longitud en esa columna, y un `UPDATE` no cambia el tipo. La migración es una revisión de Alembic nueva, en este orden:

1. Añadir una columna nueva, por ejemplo `embedding_768 vector(768)`, nullable al principio (admite filas aún sin rellenar, para no bloquear las lecturas de la columna vieja).
2. Rellenarla con el modelo nuevo, por lotes, sin borrar la columna vieja. Durante el relleno la búsqueda sigue leyendo la columna de 384. Borrar antes dejaría la biblioteca sin vectores.
3. Crear el índice HNSW de coseno sobre la columna nueva cuando el relleno ha terminado. Crearlo antes, con muchos nulos, no acelera la búsqueda real.
4. Apuntar la búsqueda y `vector_dimension` a la columna nueva. A partir de ahí el proveedor de 768 puede arrancar, porque la comprobación de dimensión compara contra la columna activa. Hasta este paso, una anchura mayor es incorrecta para el proceso en marcha.
5. Borrar la columna vieja y su índice en una revisión posterior, cuando ya no haya un proceso leyéndola.

Hasta que el paso 4 está desplegado, el API se niega a arrancar un proveedor cuya dimensión configurada no coincide con la columna activa. Eso evita una mezcla silenciosa de 384 y 768 en la misma consulta. El nombre de modelo en cada fila sigue impidiendo mezclar dos modelos de la misma anchura.

Cambiar solo el modelo de chat no reembebe nada: el chat no escribe la columna. Cambiar el tamaño de chunk tampoco reembede el texto viejo con sentido: los vectores describen las ventanas ya guardadas. Un tamaño nuevo exige regenerar los chunks, no solo los vectores.

## Búsqueda híbrida y umbral de abstención

### Qué se eligió

No se usa solo búsqueda vectorial (ordenar chunks por distancia coseno y quedarse con los más cercanos). La recuperación es híbrida (junta el parecido del vector con la presencia literal de las palabras):

- distancia coseno de pgvector sobre el embedding de la pregunta (más baja es más parecida; por encima del techo, y sin otro indicio, se rechaza);
- texto completo de PostgreSQL (busca las palabras, no el parecido) con el diccionario `simple` (no recorta sufijos; un diccionario que stemiza convertiría `HX-200` o un número de pieza en otra cadena y la búsqueda literal fallaría), en la columna generada `tsv` (el índice de palabras, calculado solo a partir del texto del chunk);
- fusión por rango recíproco (suma, para cada chunk, `1 / (k + puesto)` en cada lista; el puesto 1 aporta más que el puesto 10, y un chunk que sale en las dos listas suma las dos aportaciones; una puntuación más alta es un mejor acuerdo). `RRF_K = 60` (la constante `k` de esa fórmula, no el número de resultados; un `k` menor exagera al primero de la lista, un `k` mayor aplana puestos y el primero apenas destaca; 60 es el valor habitual de esta fusión, elegido para que el segundo puesto siga contando).

El índice GIN (índice de palabras sueltas, rápido para "esta página contiene NB-IoT") sobre `tsv` y el HNSW sobre el vector conviven desde la migración inicial. Hacen preguntas distintas: uno responde "¿está la palabra?" y el otro "¿se parece el texto?".

Además hay dos caminos que no pasan por el umbral vectorial (el techo de distancia), porque la pregunta ya trae la evidencia y el coseno solo estorbaría:

- las preguntas de catálogo (qué modelos hay, quién fabrica un modelo) se responden con los metadatos del documento (columnas `maker` y `equipment_model`, no el texto troceado);
- las comparaciones de tensión de alimentación y de temperatura de operación se leen de los rangos impresos. "Más de 12 V" usa el límite superior de un rango de alimentación. "9–32 V" cumple porque 32 es mayor que 12. "No superar 12 V" no cumple: es un máximo que no pasa de 12. La temperatura de almacenamiento o de carga no cuenta, porque la pregunta de operación no pide esos rangos. Un límite superior más alto es el que gana en "cuál es la tensión mayor".

### Cuándo se decide que no hay evidencia

Hay tres compuertas (condiciones que rechazan la búsqueda vectorial). No todas se aplican a todas las preguntas.

| Compuerta | Valor | Qué extremo es el correcto | Efecto |
| --- | --- | --- | --- |
| Techo de coseno (`MAX_COSINE_DISTANCE`) | 0,64 | La distancia buena es la más baja. El techo es la distancia máxima admitida: por encima de 0,64 el chunk más cercano está demasiado lejos. Un techo más bajo rechaza aciertos (0,45 lo hacía). Un techo más alto deja pasar preguntas cuyas palabras no están en ningún manual. | Si el chunk más cercano está más lejos y la pregunta no está acotada a un manual, la búsqueda se abstiene (decide que no hay evidencia y no llama al modelo). |
| Margen de vecinos (`RETRIEVAL_NEIGHBOR_MARGIN`) | 0,03 | Es una holgura que se suma a la distancia del ganador. Un margen mayor conserva más páginas y también más ruido. Un margen 0 se queda solo con las que están tan cerca como el ganador. 0,03 es estrecho a propósito. | Si el más cercano pasó el techo, también se conservan los que están a 0,03 o menos de él. |
| Suelo de fusión (`MIN_FUSED_SCORE`) | 0,01 | La puntuación buena es la más alta. El suelo es la puntuación mínima: por debajo se abstiene. Subirlo exigiría que el chunk saliera muy arriba en las dos listas. Bajarlo a 0 aceptaría una fusión vacía. | 0,01 deja pasar un solo hit de rango recíproco con `k = 60` (`1 / (60 + 1) ≈ 0,016`) y rechaza una lista sin nadie. |

La abstención de búsqueda devuelve "The manuals do not contain enough evidence to answer." con HTTP 200 y `answered: false`. No es un error del servicio: el servicio sí supo que los manuales no alcanzan. Si el modelo de chat está caído después de haber encontrado pasajes, la respuesta es HTTP 503 (el servicio no pudo completar la prosa) y los pasajes viajan igual, para que el técnico los lea.

El techo de 0,64 no se aplica cuando la pregunta ya nombra un título o un modelo de la biblioteca, o cuando el cliente filtró por `equipmentModel` (el modelo que el técnico eligió en el formulario; es un filtro duro, no una pista). En esos casos el manual ya está elegido y el vector solo ordena dentro de él. Aplicar el techo ahí rechazaría el propio manual: un nombre corto contra una página larga hashea cerca de distancia 0,8 (muy lejos; peor que 0,64), aunque la página contenga el nombre. Una pregunta que solo nombra un producto devuelve todas las páginas de ese manual, no las `k` primeras. `k` (cuántos chunks se devuelven al final; más alto muestra más pasajes y más ruido) por defecto es 5. El pool de candidatos (cuántos chunks se miran antes de fusionar y cortar a `k`; más alto recuerda mejor y cuesta más) es 20. Para "qué dispositivos tienen NB-IoT" no se corta a 5, porque el sexto dispositivo también es parte de la respuesta.

### Por qué no basta el vector

El embedder de calibración es un hash de bolsa de palabras (cada palabra suma en una casilla fija del vector de 384; no entiende sinónimos, solo coincidencia de palabras). Una pregunta corta contra un chunk largo cae cerca de distancia coseno 0,55–0,63 cuando comparten palabras (por debajo del techo: se aceptan), y cerca de 0,65 o peor cuando no (por encima del techo: se rechazan). Un nombre de producto corto contra una página larga de datasheet cae cerca de 0,8 aunque la página contenga ese nombre. Si la única compuerta fuera el coseno, "HX-200" no abriría su propio manual y "NB-IoT" se perdería en la página que lo imprime si el hash queda lejos. Por eso la búsqueda no es solo vectorial: el vector ordena, y las palabras rescatan la página que sí las contiene.

Un pasaje que contiene las palabras de contenido de la pregunta (las que no son "qué", "los" o "dispositivo") se conserva aunque su coseno pase de 0,64. Se guarda un pasaje por manual, no los veinte chunks globalmente más cercanos. Si se guardaran solo los veinte más cercanos, el manual cuyo único chunk relevante hashea un poco peor desaparecería, y una pregunta de "qué dispositivos" mentiría por omisión. "CAN bus" casa con "CANbus" porque se busca también el compuesto (las dos palabras pegadas). Dos grafías del mismo rasgo son el mismo término si están en un grupo de alias (lista editable de grafías equivalentes, por tenant). Una palabra de la pregunta de ocho letras o más, a una letra de distancia de un alias (una sustitución, un añadido o una falta; más de una letra ya es otra palabra), entra en ese grupo: "desconnection" encuentra "disconnection". La palabra larga tiene que estar: "battery" solo no responde una pregunta de desconexión, porque bajar esa exigencia contestaría con cualquier página que mencione la batería. Un typo de una letra en una palabra de función, como "supoorting", se pliega a "supporting" y no se exige en la página: exigir el typo haría que ninguna página coincidiera. Una mención negada ("not", "no", "sin", "without" en los 60 caracteres anteriores; una ventana más corta perdería el "no" de la frase previa, una más larga marcaría como negación un "no" de otro párrafo) no cuenta como evidencia afirmativa. Sin ese filtro, un dispositivo que dice "NB-IoT no está disponible" saldría en la lista de los que sí lo tienen.

Ese camino léxico (recuperar por las palabras, no por la distancia) es también lo que permite usar `all-minilm` en Docker sin haber recalibrado el 0,64 para las distancias de MiniLM. Las distancias de un embedder real no se parecen a las del hash: un parecido real suele caer bastante por debajo de 0,64, así que el techo deja de ser el filtro fino y pasa a ser una red de seguridad. Las preguntas cuyas palabras están en el manual siguen encontrando la página por el camino léxico. Las preguntas cuyas palabras no están siguen cayendo en el techo. El conjunto de evaluación, en cambio, está calibrado con el hash: `make eval` asume esas distancias. Volver a calibrar el techo para MiniLM exigiría medir de nuevo aciertos y el fallo de la pintura de cabina; hasta entonces, subir o bajar 0,64 a ciegas movería la abstención sin una medida.

### Cómo se calibró el 0,64

El primer techo fue 0,45. Es un valor más bajo, es decir más exigente: solo acepta parecidos muy fuertes. Abstuvo en preguntas verdaderas, porque el hash de una pregunta corta contra un chunk de unos 800 caracteres casi nunca baja de 0,45 aunque las palabras coincidan. Bajar el techo todavía más habría empeorado eso. Había que subirlo hasta rozar los aciertos peores, sin llegar al fallo.

Se midió el corpus de muestra (los manuales HX-200 y TU-9 que siembran la biblioteca vacía):

- las preguntas cuyas palabras están en el manual caen entre unos 0,30 y 0,63 (todas por debajo de un techo de 0,64, así que se aceptan);
- "What is the cabin paint color of the ZX-1?", cuyas palabras no están en ningún manual, cae hacia 0,65 (por encima de 0,64, así que se rechaza).

El techo se dejó en **0,64**: por encima del peor acierto observado en ese conjunto (0,63) y por debajo del fallo conocido (0,65). No es una constante universal de coseno. Es el corte de este embedder de hash contra estos chunks de unos 800 caracteres. Otro embedder, u otros tamaños de chunk, moverían esos dos números y el 0,64 dejaría de separar el acierto del fallo.

El margen de 0,03 salió de una pregunta amplia, "everything about the HX-200". La página de frenos hasheaba hacia 0,64 y la de hidráulicos hacia 0,65. Sin el margen, la respuesta se quedaba en una sola página, la un poco más cercana. Con 0,03, la página vecina entra una vez que la más cercana ya pasó el techo. Un margen de 0,10 habría metido páginas claramente peores. Un margen de 0 habría ocultado la hidráulica. 0,03 es la holgura mínima que separaba esas dos páginas en la medida.

El conjunto que vigila esa calibración está en `evaluation/questions.json`:

| Pregunta | Qué tiene que pasar |
| --- | --- |
| Grosor mínimo de la pastilla del HX-200 | el pasaje contiene "4.2 mm" dentro de los `k` primeros (hoy 5; si sale en el puesto 6, el recall falla) |
| Capacidad del depósito hidráulico del HX-200 | el pasaje contiene "18 litres" |
| Par de la antena TU-9 | el pasaje contiene "8 Nm" |
| Color de la pintura de cabina del ZX-1 | abstenerse: esas palabras no están en la biblioteca; contestar sería un falso positivo (peor que callar, porque inventa un color) |

`make eval` calcula recall (fracción de preguntas con respuesta cuya frase esperada aparece en los pasajes; más alto es mejor, el objetivo es 1) y acierto de abstención (fracción de preguntas sin evidencia que sí se callan; más alto es mejor, el objetivo es 1) sobre ese fichero. El conjunto es pequeño a propósito: tres hechos que el manual sí imprime y una pregunta que no debe inventarse. Si un cambio de ranking hace que "4.2 mm" salga del top 5, o que la pintura de cabina deje de abstenerse, el resultado baja. Los tests de recuperación cubren además los casos que el conjunto no nombra: compuestos, alias, typos de una letra y el máximo de tensión sin un número en la pregunta.

### Qué no hace el umbral

El 0,64 no decide la prosa (las frases que lee el técnico). Con `LLM_PROVIDER=fake` (sin red y sin modelo; las respuestas salen de las lecturas ya comprobadas), una comparación o un acierto léxico se devuelve tal cual. Con `litellm` (el camino de cualquier modelo real, local o en la nube), esos pasajes son la evidencia y el modelo escribe las frases, con la lectura ya comprobada como nota que no puede contradecir. Si el modelo se niega o cita un chunk que no se le envió, la respuesta vuelve a la lectura comprobada o a los pasajes: una prosa más fluida no compensa un número que el manual no tiene. El umbral solo decide si la búsqueda vectorial, ella sola, tiene algo que enseñar. La evidencia léxica, el catálogo y las lecturas numéricas no esperan a que el coseno esté de acuerdo, porque en esos casos la evidencia ya está en las palabras o en los metadatos y una distancia alta sería un falso rechazo.
