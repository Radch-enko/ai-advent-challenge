# Model comparison results

Run at: 2026-09-05T09:40:00.581745+00:00

## Metrics

| Model | Time, s | Input tokens | Output tokens | Total tokens | Cost, USD |
| --- | ---: | ---: | ---: | ---: | ---: |
| gpt-5.6-luna | 6.24 | 31 | 384 | 415 | $0.000467 |
| gpt-5.6-terra | 4.83 | 31 | 275 | 306 | $0.003362 |
| gpt-5.6-sol | 5.89 | 31 | 321 | 352 | $0.006544 |

## Prompt

Напиши функцию на kotlin для валидации даты рождения пользователя. Требования: пользователь должен быть старше 18 лет

## Answers

### gpt-5.6-luna

```kotlin
import java.time.Clock
import java.time.LocalDate
import java.time.ZoneId

/**
 * Проверяет, что пользователь старше 18 лет.
 * Дата рождения ровно 18 лет назад не подходит:
 * пользователь должен быть именно старше 18.
 */
fun isOlderThan18(
    birthDate: LocalDate,
    clock: Clock = Clock.systemDefaultZone()
): Boolean {
    val today = LocalDate.now(clock)
    val date18YearsAgo = today.minusYears(18)

    return birthDate.isBefore(date18YearsAgo)
}
```

Пример использования:

```kotlin
val birthDate = LocalDate.of(2000, 5, 10)

if (isOlderThan18(birthDate)) {
    println("Пользователь может продолжить")
} else {
    println("Пользователь должен быть старше 18 лет")
}
```

Если пользователь должен быть **не младше 18 лет**, включая тех, кому исполнилось ровно 18, используйте `!isAfter`:

```kotlin
fun isAtLeast18(
    birthDate: LocalDate,
    clock: Clock = Clock.systemDefaultZone()
): Boolean {
    val today = LocalDate.now(clock)
    return !birthDate.isAfter(today.minusYears(18))
}
```

### gpt-5.6-terra

```kotlin
import java.time.Clock
import java.time.LocalDate

fun isOlderThan18(birthDate: LocalDate, clock: Clock = Clock.systemDefaultZone()): Boolean {
    val today = LocalDate.now(clock)
    val eighteenthBirthday = birthDate.plusYears(18)

    return today.isAfter(eighteenthBirthday)
}
```

Пример использования:

```kotlin
val birthDate = LocalDate.of(2005, 3, 10)

if (isOlderThan18(birthDate)) {
    println("Пользователь старше 18 лет")
} else {
    println("Пользователь младше 18 лет или ему ровно 18")
}
```

Функция использует строгое условие «старше 18»: пользователь, которому исполнилось 18 сегодня, вернёт `false`.

### gpt-5.6-sol

```kotlin
import java.time.Clock
import java.time.LocalDate

fun isValidBirthDate(
    birthDate: LocalDate,
    clock: Clock = Clock.systemDefaultZone()
): Boolean {
    val today = LocalDate.now(clock)
    val eighteenthBirthday = birthDate.plusYears(18)

    // Строго старше 18 лет, а не «18 лет и старше»
    return eighteenthBirthday.isBefore(today)
}
```

Пример:

```kotlin
val birthDate = LocalDate.of(2000, 5, 15)

if (isValidBirthDate(birthDate)) {
    println("Дата рождения валидна")
} else {
    println("Пользователь должен быть старше 18 лет")
}
```

Если под требованием подразумевается **«18 лет и старше»**, условие нужно заменить:

```kotlin
return !birthDate.plusYears(18).isAfter(today)
```
