# GigaChat model comparison results

Run at: 2026-09-05T09:23:04.868174+00:00

## Metrics

| Model | Time, s | Input tokens | Output tokens | Billable tokens | Cost, RUB |
| --- | ---: | ---: | ---: | ---: | ---: |
| GigaChat-2 | 3.89 | 213 | 619 | 832 | ₽0.0541 |
| GigaChat-2-Pro | 10.04 | 208 | 500 | 708 | ₽0.3540 |
| GigaChat-2-Max | 10.57 | 210 | 698 | 908 | ₽0.5902 |

## Prompt

Найди ошибки в коде: 
class Task(var id: Long, val name: String)

val list = listOf(1, 3, 5)
val tasks = HashSet<Task>()

fun main() {
    val task1 = Task(1, "Задача")
    val task2 = Task(1, "Задача")

    tasks.add(task1)
    tasks.add(task2)

    list.add(7)

    list.forEvery { it ->
        if (it == 3) {
            return
        }
        println("$it")
    }

    println("tasks contains ${tasks.size} elements")
    println("Done!")
}

synchronized fun <reified T> List<T>.forEvery(itemAction: (T) -> Unit) {
    list.reversed().forEach { itemAction(it) }
}

// Компилируется ли код? Если нет, то поправить проблемные места.

## Answers

### GigaChat-2

Код содержит несколько ошибок и проблемных мест:

### Ошибки и проблемы:

1. **Ошибка компиляции:**  
   Метод `add()` отсутствует у типа `List<Int>` (список чисел). Списки в Kotlin неизменяемы, метод `add()` доступен только для коллекций, реализующих интерфейс `MutableList`.
   
   Исправление: заменить `list.add(...)` на корректный вариант добавления элемента в коллекцию, например, через `mutableListOf()` или использование коллекции, поддерживающей изменения (например, ArrayList):
   ```kotlin
   val mutableList = mutableListOf(1, 3, 5)
   ```

2. **Ошибка компиляции:**  
   Метод `forEvery()` объявлен синхронизированным (`synchronized`), однако он предназначен для обработки элементов списка, а не для синхронизации потоков. Синхронизация здесь бессмысленна и приведет к ошибкам при попытке параллельного исполнения.

   Исправление: убрать ключевое слово `synchronized`.

3. **Проблема дублирования объектов:**  
   Объекты класса `Task` создаются с одинаковым значением поля `id`, но разные экземпляры объекта. Это значит, что два объекта с одинаковыми полями (`id=1`) будут считаться разными объектами, а не одним и тем же объектом. Для устранения этой проблемы лучше сделать поле `id` уникальным либо воспользоваться конструкцией копирования существующего объекта.

   Пример исправленного варианта:
   ```kotlin
   val task1 = Task(1, "Задача")
   val task2 = task1.copy()
   ```

4. **Неправильный синтаксис метода forEvery():**  
   У вас неверно указан тип параметра в лямбде. Вместо `it ->` должно быть `(T)` → `(item: T) ->`.

   Исправленный вариант:
   ```kotlin
   list.forEach { item -> // или list.forEach { item: Int -> ...
       if (item == 3) {
           return
       }
       println("$item")
   }
```

---

Исправленный рабочий код выглядит следующим образом:

```kotlin
class Task(var id: Long, val name: String)

val mutableList = mutableListOf(1, 3, 5)
val tasks = HashSet<Task>()

fun main() {
    val task1 = Task(1, "Задача")
    val task2 = task1.copy()
    
    tasks.add(task1)
    tasks.add(task2)

    mutableList.add(7)

    mutableList.forEach { item ->
        if (item == 3) {
            return
        }
        println("$item")
    }

    println("tasks contains ${tasks.size} elements")
    println("Done!")
}

fun <T> List<T>.forEvery(itemAction: (T) -> Unit) {
    this.reversed().forEach { itemAction(it) }
}
```

Теперь код успешно компилируется и работает правильно.

### GigaChat-2-Pro

Вот исправленный рабочий вариант кода с пояснением ошибок:

### Ошибки и проблемы:

1. **Ошибка №1:**  
   Нельзя изменить содержимое неизменяемого списка `listOf()`:
   ```kotlin
   list.add(7)
   ```
   Исправление: заменить `listOf()` на `mutableListOf()`, чтобы список стал изменяемым.

2. **Ошибка №2:**  
   Метод `forEvery()` объявлен синхронизированным, но неправильно использован оператор `return` внутри цикла:
   ```kotlin
   list.forEvery { it ->
       if (it == 3) {
           return // ошибка компиляции: возврат из лямбды нарушает область видимости
       }
   }
   ```
   Исправление: заменить `return` на `return@forEvery`, чтобы корректно выйти из замыкания.

3. **Ошибка №3:**  
   Внутри метода расширения некорректно обращение к переменной `list`:
   ```kotlin
   synchronized fun <reified T> List<T>.forEvery(itemAction: (T) -> Unit) {
       list.reversed().forEach { itemAction(it) } // ошибка: переменная list не существует здесь
   }
   ```
   Исправление: использовать ключевое слово `this` для обращения к самому объекту коллекции.

---

### Исправленный рабочий код:
```kotlin
class Task(val id: Long, val name: String)

val list = mutableListOf(1, 3, 5) // исправлено на изменяемый список
val tasks = HashSet<Task>()

fun main() {
    val task1 = Task(1, "Задача")
    val task2 = Task(1, "Задача")

    tasks.add(task1)
    tasks.add(task2)

    list.add(7)

    list.forEvery { it ->
        if (it == 3) {
            return@forEvery // исправлен выход из замыкания
        }
        println("$it")
    }

    println("tasks contains ${tasks.size} elements")
    println("Done!")
}

// Исправленная версия метода расширения
synchronized fun <T> List<T>.forEvery(itemAction: (T) -> Unit) {
    this.reversed().forEach { itemAction(it) } // правильно обращаемся через this
}
```

Теперь код успешно компилируется и работает корректно.

### GigaChat-2-Max

Код содержит несколько ошибок и потенциальных проблем:

### Ошибки и проблемы:

1. **Ошибка компиляции в методе `list.add(7)`**  
   Объект `list` объявлен как неизменяемый (`val list = listOf(...)`), следовательно, попытка добавить элемент вызовет ошибку компиляции.
   
   Решение: заменить `listOf()` на `mutableListOf()` либо удалить попытку добавления элемента.

2. **Проблема дубликатов в множестве `HashSet<Task>`**  
   Класс `Task` не переопределяет методы `equals()` и `hashCode()`, поэтому два объекта с одинаковыми полями будут считаться разными объектами, и оба попадут в множество. Чтобы избежать дубликатов, нужно реализовать эти методы.

3. **Неправильная реализация метода расширения `forEvery`**  
   Метод расширения принимает параметр типа `reified T`, однако тип параметра уже известен заранее, и использование ключевого слова `reified` здесь неуместно. К тому же метод пытается изменить оригинальный список через обращение к `list.reversed()`, что неверно, поскольку `reversed()` возвращает новый список, а не меняет существующий.

4. **Использование ключевого слова synchronized некорректно**  
   Ключевое слово `synchronized` применяется неправильно, так как оно предназначено для синхронизации потоков, а здесь потоковая безопасность не нужна. Его лучше убрать.

5. **Метод `return` внутри лямбды**  
   Использование простого `return` приведет к преждевременному выходу из всего метода `main()`. Вместо этого нужно использовать квалифицированное возвращение `return@forEvery`.

---

### Исправленный код:
```kotlin
data class Task(val id: Long, val name: String) // Используем data-класс для автоматического equals/hashCode/toString

val list = mutableListOf(1, 3, 5) // Делаем список изменяемым

val tasks = HashSet<Task>() // Хранилище уникальных объектов Task

fun main() {
    val task1 = Task(1, "Задача")
    val task2 = Task(1, "Задача")
    
    tasks.add(task1)
    tasks.add(task2) // Теперь второй объект не добавляется, так как равен первому

    list.add(7) // теперь корректно работает благодаря mutableListOf()

    list.forEvery { it ->
        if (it == 3) {
            return@forEvery // Возвращаемся только из лямбды, а не из всей функции main
        }
        println("$it")
    }

    println("tasks contains ${tasks.size} elements")
    println("Done!")
}

fun <T> List<T>.forEvery(action: (T) -> Unit) { // Убираем reified и synchronized
    reversed().forEach(action) // Корректно применяем действие к перевёрнутому списку
}
```

### Что изменилось?
- Заменили класс `Task` на `data class`, чтобы автоматически получить правильные реализации методов сравнения и хеширования.
- Сделали список изменяемым с помощью `mutableListOf`.
- Удалили ненужное ключевое слово `reified` и убрали `synchronized`.
- Изменили возврат из лямбды на локальное возвращение `return@forEvery`.
- Реализовали правильную обработку списка методом `.reversed()`.

Теперь код успешно компилируется и выполняется правильно.
