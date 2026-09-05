# GigaChat model comparison results

Run at: 2026-09-05T09:03:52.019476+00:00

## Metrics

| Model | Time, s | Input tokens | Output tokens | Billable tokens | Cost, RUB |
| --- | ---: | ---: | ---: | ---: | ---: |
| GigaChat-2 | 2.33 | 43 | 295 | 338 | ₽0.0220 |
| GigaChat-2-Pro | 3.37 | 43 | 238 | 281 | ₽0.1405 |
| GigaChat-2-Max | 4.76 | 40 | 304 | 344 | ₽0.2236 |

## Prompt

Напиши функцию на kotlin для валидации даты рождения пользователя. Требования: пользователь должен быть старше 18 лет

## Answers

### GigaChat-2

Вот простая функция на Kotlin, проверяющая корректность даты рождения и возраст пользователя:

```kotlin
import java.time.LocalDate
import java.time.Period
import java.time.temporal.ChronoUnit

fun validateBirthDate(birthDateString: String): Boolean {
    // Парсинг строки даты в LocalDate
    val birthDate = LocalDate.parse(birthDateString)
    
    // Текущая дата
    val currentDate = LocalDate.now()
    
    // Вычисляем разницу в годах
    val age = Period.between(birthDate, currentDate).years
    
    return if (age >= 18) true else false
}
```

### Пример использования:
```kotlin
val userBirthDate = "1995-05-10"
val isValidAge = validateBirthDate(userBirthDate)

if (isValidAge) {
    println("Пользователь старше 18 лет")
} else {
    println("Пользователь младше 18 лет")
}
```

**Что делает функция:**
- Преобразует строку с датой рождения в объект `LocalDate`.
- Получает текущую дату.
- Рассчитывает разницу в годах между датой рождения и текущей датой.
- Проверяет, соответствует ли возраст минимальному порогу (старше 18 лет).

Функция возвращает `true`, если пользователь старше 18 лет, иначе — `false`.

### GigaChat-2-Pro

Вот простая и понятная функция на Kotlin для проверки возраста пользователя по дате рождения:

```kotlin
import java.time.LocalDate
import java.time.Period

fun isUserOver18(birthday: LocalDate): Boolean {
    val today = LocalDate.now()
    
    // Проверяем возраст через период между датами
    return Period.between(birthday, today).years >= 18
}
```

### Пример использования:

```kotlin
val birthday = LocalDate.of(2000, 1, 1)
if (isUserOver18(birthday)) {
    println("Пользователь старше 18 лет")
} else {
    println("Пользователю меньше 18 лет")
}
```

### Объяснение:
- Функция принимает объект типа `LocalDate`, представляющий дату рождения.
- Используется метод `Period.between()`, позволяющий корректно посчитать количество полных лет между двумя датами.
- Возвращаемое значение `true`, если пользователь достиг совершеннолетия (18 лет), иначе возвращается `false`.

Таким образом, эта функция надёжно проверяет возраст пользователя, учитывая точные календарные расчёты.

### GigaChat-2-Max

Вот простая функция на Kotlin для проверки возраста пользователя по дате рождения. Функция принимает строку формата `"dd.MM.yyyy"` и возвращает `true`, если возраст больше либо равен 18 годам, иначе — `false`.

```kotlin
import java.time.LocalDate
import java.time.Period
import java.time.format.DateTimeFormatter
import java.time.format.DateTimeParseException

fun isUserOlderThan18(birthdateString: String): Boolean {
    val formatter = DateTimeFormatter.ofPattern("dd.MM.yyyy")
    
    // Парсинг строки даты рождения
    try {
        val birthdate = LocalDate.parse(birthdateString, formatter)
        
        // Получаем сегодняшнюю дату
        val today = LocalDate.now()
        
        // Вычисляем разницу в годах
        return Period.between(birthdate, today).years >= 18
    } catch (e: DateTimeParseException) {
        throw IllegalArgumentException("Некорректный формат даты. Используйте dd.MM.yyyy")
    }
}
```

### Пример использования:

```kotlin
val dateOfBirth = "01.01.2005"
if (isUserOlderThan18(dateOfBirth)) {
    println("Пользователь достиг совершеннолетия.")
} else {
    println("Пользователь младше 18 лет.")
}
```

Эта реализация учитывает корректный формат даты и правильно обрабатывает исключения при неверном вводе.
