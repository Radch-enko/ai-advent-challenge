# Temperature experiment

- Model: `gpt-5.4-mini`
- Runs per temperature: 5
- Created: 2026-09-03T22:37:49+06:00

## Prompt

```text
напиши реализацию UseCase класса для авторизации на kotlin
```

## Summary

| Temperature | Completed runs | Avg chars | Avg words | Avg output tokens | Avg unique-word ratio | Avg pairwise similarity |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 0 | 5 | 2482.0 | 245.2 | 583.4 | 0.431 | 0.610 |
| 0.7 | 5 | 2788.6 | 277.2 | 649.6 | 0.423 | 0.313 |
| 1.7 | 5 | 2941.6 | 291.2 | 682.4 | 0.423 | 0.227 |

Lower pairwise similarity means the answers are more lexically different. It does not measure semantic quality or correctness.

## Temperature 0

| Attempt | Chars | Words | Lines | Output tokens | Reasoning tokens | Unique-word ratio |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 2205 | 219 | 99 | 516.0 | 0.0 | 0.457 |
| 2 | 2540 | 245 | 109 | 580.0 | 0.0 | 0.424 |
| 3 | 2555 | 254 | 118 | 607.0 | 0.0 | 0.425 |
| 4 | 2555 | 254 | 118 | 607.0 | 0.0 | 0.425 |
| 5 | 2555 | 254 | 118 | 607.0 | 0.0 | 0.425 |

### Attempt 1

```text
Ниже пример **UseCase-класса для авторизации** на Kotlin в стиле Clean Architecture.  
Покажу вариант с `Result`, чтобы удобно обрабатывать успех/ошибку.

### 1. Модель запроса и результата

```kotlin
data class LoginRequest(
    val email: String,
    val password: String
)

data class AuthResult(
    val token: String,
    val userId: String
)
```

### 2. Репозиторий

```kotlin
interface AuthRepository {
    suspend fun login(email: String, password: String): AuthResult
}
```

### 3. UseCase

```kotlin
class LoginUseCase(
    private val authRepository: AuthRepository
) {
    suspend operator fun invoke(request: LoginRequest): Result<AuthResult> {
        return try {
            val result = authRepository.login(
                email = request.email,
                password = request.password
            )
            Result.success(result)
        } catch (e: Exception) {
            Result.failure(e)
        }
    }
}
```

### 4. Использование

```kotlin
val loginUseCase = LoginUseCase(authRepository)

viewModelScope.launch {
    val result = loginUseCase(
        LoginRequest(
            email = "test@mail.com",
            password = "123456"
        )
    )

    result.onSuccess { auth ->
        println("Token: ${auth.token}")
    }.onFailure { error ->
        println("Login failed: ${error.message}")
    }
}
```

---

## Более “чистый” вариант с отдельными ошибками

Если хочешь более правильную архитектуру, лучше не ловить просто `Exception`, а возвращать свой тип результата:

```kotlin
sealed class LoginResult {
    data class Success(val auth: AuthResult) : LoginResult()
    data class Error(val message: String) : LoginResult()
}
```

UseCase:

```kotlin
class LoginUseCase(
    private val authRepository: AuthRepository
) {
    suspend operator fun invoke(request: LoginRequest): LoginResult {
        return try {
            val auth = authRepository.login(request.email, request.password)
            LoginResult.Success(auth)
        } catch (e: Exception) {
            LoginResult.Error(e.message ?: "Unknown error")
        }
    }
}
```

---

Если хочешь, я могу сразу написать **полный пример под MVVM + Retrofit + Repository + UseCase + ViewModel**.
```

### Attempt 2

```text
Ниже пример **UseCase-класса для авторизации** на Kotlin в стиле Clean Architecture.  
Покажу вариант с `Result`, чтобы удобно обрабатывать успех/ошибку.

### 1. Модель запроса и результата

```kotlin
data class LoginRequest(
    val email: String,
    val password: String
)

data class AuthResult(
    val token: String,
    val userId: String
)
```

### 2. Интерфейс репозитория

```kotlin
interface AuthRepository {
    suspend fun login(email: String, password: String): AuthResult
}
```

### 3. UseCase для авторизации

```kotlin
class LoginUseCase(
    private val authRepository: AuthRepository
) {
    suspend operator fun invoke(request: LoginRequest): Result<AuthResult> {
        return try {
            val result = authRepository.login(
                email = request.email,
                password = request.password
            )
            Result.success(result)
        } catch (e: Exception) {
            Result.failure(e)
        }
    }
}
```

### 4. Использование

```kotlin
val loginUseCase = LoginUseCase(authRepository)

viewModelScope.launch {
    val result = loginUseCase(
        LoginRequest(
            email = "test@mail.com",
            password = "123456"
        )
    )

    result.onSuccess { auth ->
        println("Token: ${auth.token}")
    }.onFailure { error ->
        println("Login failed: ${error.message}")
    }
}
```

---

## Если нужен более “чистый” вариант с отдельными ошибками

Можно сделать так:

```kotlin
sealed class AuthError {
    data object InvalidCredentials : AuthError()
    data object NetworkError : AuthError()
    data class Unknown(val throwable: Throwable) : AuthError()
}

sealed class LoginResult {
    data class Success(val authResult: AuthResult) : LoginResult()
    data class Error(val error: AuthError) : LoginResult()
}
```

UseCase:

```kotlin
class LoginUseCase(
    private val authRepository: AuthRepository
) {
    suspend operator fun invoke(request: LoginRequest): LoginResult {
        return try {
            val result = authRepository.login(request.email, request.password)
            LoginResult.Success(result)
        } catch (e: IllegalArgumentException) {
            LoginResult.Error(AuthError.InvalidCredentials)
        } catch (e: java.io.IOException) {
            LoginResult.Error(AuthError.NetworkError)
        } catch (e: Exception) {
            LoginResult.Error(AuthError.Unknown(e))
        }
    }
}
```

---

Если хочешь, я могу сразу написать **полный пример под MVVM + Retrofit + Repository + UseCase + ViewModel**.
```

### Attempt 3

```text
Ниже пример простой и чистой реализации `UseCase` для авторизации на Kotlin в стиле Clean Architecture.

## 1. Модель результата

```kotlin
data class AuthResult(
    val token: String,
    val userId: String
)
```

## 2. Интерфейс репозитория

```kotlin
interface AuthRepository {
    suspend fun login(email: String, password: String): AuthResult
}
```

## 3. Базовый UseCase

Если у тебя в проекте принято использовать общий базовый класс:

```kotlin
abstract class UseCase<in P, out R> {
    abstract suspend operator fun invoke(params: P): R
}
```

## 4. Параметры для авторизации

```kotlin
data class LoginParams(
    val email: String,
    val password: String
)
```

## 5. Реализация UseCase

```kotlin
class LoginUseCase(
    private val authRepository: AuthRepository
) : UseCase<LoginParams, AuthResult>() {

    override suspend operator fun invoke(params: LoginParams): AuthResult {
        require(params.email.isNotBlank()) { "Email must not be blank" }
        require(params.password.isNotBlank()) { "Password must not be blank" }

        return authRepository.login(
            email = params.email,
            password = params.password
        )
    }
}
```

## 6. Использование

```kotlin
val useCase = LoginUseCase(authRepository)

viewModelScope.launch {
    try {
        val result = useCase(
            LoginParams(
                email = "test@mail.com",
                password = "123456"
            )
        )
        println("Token: ${result.token}")
    } catch (e: Exception) {
        println("Login failed: ${e.message}")
    }
}
```

---

## Если нужен более “правильный” вариант с `Result`

Часто удобнее возвращать `Result<AuthResult>`:

```kotlin
class LoginUseCase(
    private val authRepository: AuthRepository
) {
    suspend operator fun invoke(params: LoginParams): Result<AuthResult> {
        return runCatching {
            require(params.email.isNotBlank()) { "Email must not be blank" }
            require(params.password.isNotBlank()) { "Password must not be blank" }

            authRepository.login(
                email = params.email,
                password = params.password
            )
        }
    }
}
```

Использование:

```kotlin
viewModelScope.launch {
    loginUseCase(LoginParams("test@mail.com", "123456"))
        .onSuccess { auth ->
            println(auth.token)
        }
        .onFailure { error ->
            println(error.message)
        }
}
```

---

Если хочешь, я могу сразу написать **полный пример под MVVM + Retrofit + Repository + UseCase + ViewModel**.
```

### Attempt 4

```text
Ниже пример простой и чистой реализации `UseCase` для авторизации на Kotlin в стиле Clean Architecture.

## 1. Модель результата

```kotlin
data class AuthResult(
    val token: String,
    val userId: String
)
```

## 2. Интерфейс репозитория

```kotlin
interface AuthRepository {
    suspend fun login(email: String, password: String): AuthResult
}
```

## 3. Базовый UseCase

Если у тебя в проекте принято использовать общий базовый класс:

```kotlin
abstract class UseCase<in P, out R> {
    abstract suspend operator fun invoke(params: P): R
}
```

## 4. Параметры для авторизации

```kotlin
data class LoginParams(
    val email: String,
    val password: String
)
```

## 5. Реализация UseCase

```kotlin
class LoginUseCase(
    private val authRepository: AuthRepository
) : UseCase<LoginParams, AuthResult>() {

    override suspend operator fun invoke(params: LoginParams): AuthResult {
        require(params.email.isNotBlank()) { "Email must not be blank" }
        require(params.password.isNotBlank()) { "Password must not be blank" }

        return authRepository.login(
            email = params.email,
            password = params.password
        )
    }
}
```

## 6. Использование

```kotlin
val useCase = LoginUseCase(authRepository)

viewModelScope.launch {
    try {
        val result = useCase(
            LoginParams(
                email = "test@mail.com",
                password = "123456"
            )
        )
        println("Token: ${result.token}")
    } catch (e: Exception) {
        println("Login failed: ${e.message}")
    }
}
```

---

## Если нужен более “правильный” вариант с `Result`

Часто удобнее возвращать `Result<AuthResult>`:

```kotlin
class LoginUseCase(
    private val authRepository: AuthRepository
) {
    suspend operator fun invoke(params: LoginParams): Result<AuthResult> {
        return runCatching {
            require(params.email.isNotBlank()) { "Email must not be blank" }
            require(params.password.isNotBlank()) { "Password must not be blank" }

            authRepository.login(
                email = params.email,
                password = params.password
            )
        }
    }
}
```

Использование:

```kotlin
viewModelScope.launch {
    loginUseCase(LoginParams("test@mail.com", "123456"))
        .onSuccess { auth ->
            println(auth.token)
        }
        .onFailure { error ->
            println(error.message)
        }
}
```

---

Если хочешь, я могу сразу написать **полный пример под MVVM + Retrofit + Repository + UseCase + ViewModel**.
```

### Attempt 5

```text
Ниже пример простой и чистой реализации `UseCase` для авторизации на Kotlin в стиле Clean Architecture.

## 1. Модель результата

```kotlin
data class AuthResult(
    val token: String,
    val userId: String
)
```

## 2. Интерфейс репозитория

```kotlin
interface AuthRepository {
    suspend fun login(email: String, password: String): AuthResult
}
```

## 3. Базовый UseCase

Если у тебя в проекте принято использовать общий базовый класс:

```kotlin
abstract class UseCase<in P, out R> {
    abstract suspend operator fun invoke(params: P): R
}
```

## 4. Параметры для авторизации

```kotlin
data class LoginParams(
    val email: String,
    val password: String
)
```

## 5. Реализация UseCase

```kotlin
class LoginUseCase(
    private val authRepository: AuthRepository
) : UseCase<LoginParams, AuthResult>() {

    override suspend operator fun invoke(params: LoginParams): AuthResult {
        require(params.email.isNotBlank()) { "Email must not be blank" }
        require(params.password.isNotBlank()) { "Password must not be blank" }

        return authRepository.login(
            email = params.email,
            password = params.password
        )
    }
}
```

## 6. Использование

```kotlin
val useCase = LoginUseCase(authRepository)

viewModelScope.launch {
    try {
        val result = useCase(
            LoginParams(
                email = "test@mail.com",
                password = "123456"
            )
        )
        println("Token: ${result.token}")
    } catch (e: Exception) {
        println("Login failed: ${e.message}")
    }
}
```

---

## Если нужен более “правильный” вариант с `Result`

Часто удобнее возвращать `Result<AuthResult>`:

```kotlin
class LoginUseCase(
    private val authRepository: AuthRepository
) {
    suspend operator fun invoke(params: LoginParams): Result<AuthResult> {
        return runCatching {
            require(params.email.isNotBlank()) { "Email must not be blank" }
            require(params.password.isNotBlank()) { "Password must not be blank" }

            authRepository.login(
                email = params.email,
                password = params.password
            )
        }
    }
}
```

Использование:

```kotlin
viewModelScope.launch {
    loginUseCase(LoginParams("test@mail.com", "123456"))
        .onSuccess { auth ->
            println(auth.token)
        }
        .onFailure { error ->
            println(error.message)
        }
}
```

---

Если хочешь, я могу сразу написать **полный пример под MVVM + Retrofit + Repository + UseCase + ViewModel**.
```

## Temperature 0.7

| Attempt | Chars | Words | Lines | Output tokens | Reasoning tokens | Unique-word ratio |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 2296 | 247 | 101 | 559.0 | 0.0 | 0.397 |
| 2 | 3360 | 326 | 140 | 755.0 | 0.0 | 0.383 |
| 3 | 2701 | 266 | 120 | 647.0 | 0.0 | 0.429 |
| 4 | 2948 | 287 | 134 | 677.0 | 0.0 | 0.467 |
| 5 | 2638 | 260 | 115 | 610.0 | 0.0 | 0.438 |

### Attempt 1

```text
Ниже — пример реализации `UseCase` для авторизации на Kotlin в стиле Clean Architecture.

### 1. Модель запроса и результата

```kotlin
data class LoginRequest(
    val email: String,
    val password: String
)

data class AuthResult(
    val token: String,
    val userId: String
)
```

### 2. Интерфейс репозитория

```kotlin
interface AuthRepository {
    suspend fun login(email: String, password: String): AuthResult
}
```

### 3. Базовый UseCase

Если у тебя есть общий базовый класс:

```kotlin
abstract class UseCase<in P, out R> {
    abstract suspend fun execute(params: P): R
}
```

### 4. Реализация UseCase для авторизации

```kotlin
class LoginUseCase(
    private val authRepository: AuthRepository
) : UseCase<LoginRequest, AuthResult>() {

    override suspend fun execute(params: LoginRequest): AuthResult {
        require(params.email.isNotBlank()) { "Email не должен быть пустым" }
        require(params.password.isNotBlank()) { "Пароль не должен быть пустым" }

        return authRepository.login(
            email = params.email,
            password = params.password
        )
    }
}
```

---

## Вариант с `operator fun invoke()`
Часто в Kotlin `UseCase` делают через `invoke`, чтобы вызывать его как функцию:

```kotlin
class LoginUseCase(
    private val authRepository: AuthRepository
) {
    suspend operator fun invoke(email: String, password: String): AuthResult {
        require(email.isNotBlank()) { "Email не должен быть пустым" }
        require(password.isNotBlank()) { "Пароль не должен быть пустым" }

        return authRepository.login(email, password)
    }
}
```

Использование:

```kotlin
val result = loginUseCase("test@mail.com", "123456")
```

---

## Если нужна обработка ошибок

Можно вернуть `Result<AuthResult>`:

```kotlin
class LoginUseCase(
    private val authRepository: AuthRepository
) {
    suspend operator fun invoke(email: String, password: String): Result<AuthResult> {
        return runCatching {
            require(email.isNotBlank()) { "Email не должен быть пустым" }
            require(password.isNotBlank()) { "Пароль не должен быть пустым" }

            authRepository.login(email, password)
        }
    }
}
```

---

Если хочешь, я могу сразу написать **полный пример под MVVM + Retrofit + Repository + ViewModel**.
```

### Attempt 2

```text
Ниже пример **UseCase для авторизации** на Kotlin в стиле Clean Architecture.  
Покажу простой и практичный вариант: `LoginUseCase`, который принимает email/пароль и возвращает результат авторизации.

## 1. Модели

```kotlin
data class LoginRequest(
    val email: String,
    val password: String
)

data class AuthUser(
    val id: String,
    val email: String,
    val token: String
)
```

## 2. Репозиторий

UseCase обычно не знает, **как именно** выполняется авторизация — он вызывает репозиторий.

```kotlin
interface AuthRepository {
    suspend fun login(email: String, password: String): AuthUser
}
```

## 3. UseCase

### Вариант с `operator fun invoke()`

```kotlin
class LoginUseCase(
    private val authRepository: AuthRepository
) {
    suspend operator fun invoke(request: LoginRequest): Result<AuthUser> {
        return try {
            val user = authRepository.login(
                email = request.email,
                password = request.password
            )
            Result.success(user)
        } catch (e: Exception) {
            Result.failure(e)
        }
    }
}
```

## 4. Использование

```kotlin
class AuthViewModel(
    private val loginUseCase: LoginUseCase
) : ViewModel() {

    fun login(email: String, password: String) {
        viewModelScope.launch {
            val result = loginUseCase(
                LoginRequest(
                    email = email,
                    password = password
                )
            )

            result.onSuccess { user ->
                // Успешный вход
                println("Welcome ${user.email}")
            }.onFailure { error ->
                // Обработка ошибки
                println("Login failed: ${error.message}")
            }
        }
    }
}
```

---

## 5. Более “чистый” вариант с отдельным результатом

Если не хочешь использовать `Result`, можно сделать свой sealed class:

```kotlin
sealed class LoginResult {
    data class Success(val user: AuthUser) : LoginResult()
    data class Error(val message: String) : LoginResult()
}
```

UseCase:

```kotlin
class LoginUseCase(
    private val authRepository: AuthRepository
) {
    suspend operator fun invoke(request: LoginRequest): LoginResult {
        return try {
            val user = authRepository.login(request.email, request.password)
            LoginResult.Success(user)
        } catch (e: Exception) {
            LoginResult.Error(e.message ?: "Unknown error")
        }
    }
}
```

---

## 6. Если нужна валидация перед авторизацией

Можно добавить проверку email и пароля прямо в UseCase:

```kotlin
class LoginUseCase(
    private val authRepository: AuthRepository
) {
    suspend operator fun invoke(request: LoginRequest): LoginResult {
        if (request.email.isBlank()) {
            return LoginResult.Error("Email не может быть пустым")
        }

        if (request.password.length < 6) {
            return LoginResult.Error("Пароль должен содержать минимум 6 символов")
        }

        return try {
            val user = authRepository.login(request.email, request.password)
            LoginResult.Success(user)
        } catch (e: Exception) {
            LoginResult.Error(e.message ?: "Unknown error")
        }
    }
}
```

---

Если хочешь, я могу сразу написать **полный пример под MVVM + Hilt + Retrofit + Coroutines** для авторизации на Kotlin.
```

### Attempt 3

```text
Ниже пример простой и практичной реализации `UseCase` для авторизации на Kotlin в стиле Clean Architecture.

## 1. Модель результата

```kotlin
data class AuthResult(
    val token: String,
    val userId: String
)
```

## 2. Интерфейс репозитория

```kotlin
interface AuthRepository {
    suspend fun login(email: String, password: String): AuthResult
}
```

## 3. Базовый UseCase

Если у тебя в проекте есть общий базовый класс для use case:

```kotlin
abstract class UseCase<in P, R> {
    abstract suspend operator fun invoke(params: P): R
}
```

## 4. Параметры для авторизации

```kotlin
data class LoginParams(
    val email: String,
    val password: String
)
```

## 5. Реализация UseCase

```kotlin
class LoginUseCase(
    private val authRepository: AuthRepository
) : UseCase<LoginParams, AuthResult>() {

    override suspend operator fun invoke(params: LoginParams): AuthResult {
        require(params.email.isNotBlank()) { "Email не должен быть пустым" }
        require(params.password.isNotBlank()) { "Пароль не должен быть пустым" }

        return authRepository.login(
            email = params.email,
            password = params.password
        )
    }
}
```

## 6. Пример использования

```kotlin
val loginUseCase = LoginUseCase(authRepository)

viewModelScope.launch {
    try {
        val result = loginUseCase(
            LoginParams(
                email = "test@mail.com",
                password = "123456"
            )
        )
        println("Token: ${result.token}")
    } catch (e: IllegalArgumentException) {
        println("Validation error: ${e.message}")
    } catch (e: Exception) {
        println("Login failed: ${e.message}")
    }
}
```

---

## Если нужен более “чистый” вариант с `Result`

Часто удобнее возвращать `Result<AuthResult>`:

```kotlin
class LoginUseCase(
    private val authRepository: AuthRepository
) {
    suspend operator fun invoke(params: LoginParams): Result<AuthResult> {
        return runCatching {
            require(params.email.isNotBlank()) { "Email не должен быть пустым" }
            require(params.password.isNotBlank()) { "Пароль не должен быть пустым" }

            authRepository.login(
                email = params.email,
                password = params.password
            )
        }
    }
}
```

Использование:

```kotlin
viewModelScope.launch {
    loginUseCase(LoginParams("test@mail.com", "123456"))
        .onSuccess { auth ->
            println("Success: ${auth.token}")
        }
        .onFailure { error ->
            println("Error: ${error.message}")
        }
}
```

---

Если хочешь, я могу сразу написать **полную реализацию под MVVM + Retrofit + Repository + UseCase + ViewModel**.
```

### Attempt 4

```text
Ниже пример **UseCase для авторизации** на Kotlin в стиле Clean Architecture.  
Покажу вариант с `Result`, чтобы удобно обрабатывать успех и ошибку.

## 1. Модели

```kotlin
data class LoginRequest(
    val email: String,
    val password: String
)

data class AuthResult(
    val userId: String,
    val token: String
)
```

---

## 2. Репозиторий

UseCase обычно не ходит напрямую в сеть, а работает через интерфейс репозитория.

```kotlin
interface AuthRepository {
    suspend fun login(email: String, password: String): AuthResult
}
```

---

## 3. UseCase

```kotlin
class LoginUseCase(
    private val authRepository: AuthRepository
) {
    suspend operator fun invoke(request: LoginRequest): Result<AuthResult> {
        return try {
            val result = authRepository.login(
                email = request.email,
                password = request.password
            )
            Result.success(result)
        } catch (e: Exception) {
            Result.failure(e)
        }
    }
}
```

---

## 4. Пример использования

```kotlin
class LoginViewModel(
    private val loginUseCase: LoginUseCase
) : ViewModel() {

    fun login(email: String, password: String) {
        viewModelScope.launch {
            val result = loginUseCase(
                LoginRequest(email = email, password = password)
            )

            result.onSuccess { authResult ->
                // Успешная авторизация
                println("Token: ${authResult.token}")
            }.onFailure { error ->
                // Ошибка авторизации
                println("Login failed: ${error.message}")
            }
        }
    }
}
```

---

## 5. Более “чистый” вариант с отдельными ошибками

Если хочешь более контролируемую обработку ошибок, можно сделать так:

```kotlin
sealed class AuthError(message: String) : Exception(message) {
    object InvalidCredentials : AuthError("Invalid credentials")
    object NetworkError : AuthError("Network error")
    object UnknownError : AuthError("Unknown error")
}
```

И UseCase:

```kotlin
class LoginUseCase(
    private val authRepository: AuthRepository
) {
    suspend operator fun invoke(email: String, password: String): AuthResult {
        if (email.isBlank() || password.isBlank()) {
            throw IllegalArgumentException("Email and password must not be blank")
        }

        return authRepository.login(email, password)
    }
}
```

---

## 6. Если нужен именно Android/Domain стиль

Можно сделать UseCase как отдельный класс с `operator fun invoke()`:

```kotlin
class LoginUseCase @Inject constructor(
    private val authRepository: AuthRepository
) {
    suspend operator fun invoke(email: String, password: String): AuthResult {
        return authRepository.login(email, password)
    }
}
```

---

Если хочешь, я могу сразу написать **полный пример авторизации**:
- `Repository`
- `UseCase`
- `ViewModel`
- `Retrofit API`
- `DTO -> Domain mapper`

в одном готовом коде.
```

### Attempt 5

```text
Ниже пример **UseCase для авторизации** на Kotlin в стиле Clean Architecture.  
Покажу **базовую реализацию**, которую можно легко адаптировать под ваш проект.

---

## 1) Модель результата

```kotlin
data class AuthResult(
    val userId: String,
    val token: String
)
```

---

## 2) Интерфейс репозитория

UseCase обычно не знает, как именно происходит авторизация — через API, БД и т.д.  
Он работает через абстракцию:

```kotlin
interface AuthRepository {
    suspend fun login(email: String, password: String): AuthResult
}
```

---

## 3) UseCase для авторизации

```kotlin
class LoginUseCase(
    private val authRepository: AuthRepository
) {
    suspend operator fun invoke(
        email: String,
        password: String
    ): Result<AuthResult> {
        return try {
            if (email.isBlank() || password.isBlank()) {
                return Result.failure(IllegalArgumentException("Email и пароль не должны быть пустыми"))
            }

            val result = authRepository.login(email, password)
            Result.success(result)
        } catch (e: Exception) {
            Result.failure(e)
        }
    }
}
```

---

## 4) Пример использования

```kotlin
class LoginViewModel(
    private val loginUseCase: LoginUseCase
) : ViewModel() {

    fun login(email: String, password: String) {
        viewModelScope.launch {
            val result = loginUseCase(email, password)

            result.onSuccess { authResult ->
                // Успешная авторизация
                println("Token: ${authResult.token}")
            }.onFailure { error ->
                // Ошибка
                println("Login error: ${error.message}")
            }
        }
    }
}
```

---

## 5) Если нужен более “чистый” вариант без `Result`

Иногда в проекте делают отдельную модель ответа:

```kotlin
sealed class LoginState {
    data class Success(val data: AuthResult) : LoginState()
    data class Error(val message: String) : LoginState()
}
```

UseCase:

```kotlin
class LoginUseCase(
    private val authRepository: AuthRepository
) {
    suspend operator fun invoke(email: String, password: String): LoginState {
        if (email.isBlank() || password.isBlank()) {
            return LoginState.Error("Email и пароль не должны быть пустыми")
        }

        return try {
            val result = authRepository.login(email, password)
            LoginState.Success(result)
        } catch (e: Exception) {
            LoginState.Error(e.message ?: "Unknown error")
        }
    }
}
```

---

Если хочешь, я могу сразу написать **полную реализацию под MVVM + Retrofit + Repository + UseCase + ViewModel**.
```

## Temperature 1.7

| Attempt | Chars | Words | Lines | Output tokens | Reasoning tokens | Unique-word ratio |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 2151 | 217 | 104 | 522.0 | 0.0 | 0.392 |
| 2 | 2564 | 258 | 108 | 619.0 | 0.0 | 0.430 |
| 3 | 2760 | 276 | 106 | 653.0 | 0.0 | 0.471 |
| 4 | 2497 | 250 | 101 | 579.0 | 0.0 | 0.452 |
| 5 | 4736 | 455 | 197 | 1039.0 | 0.0 | 0.371 |

### Attempt 1

```text
Ниже пример типичной реализации `UseCase` для авторизации на Kotlin в стиле Clean Architecture.

### 1. Базовый UseCase
```kotlin
interface UseCase<P, R> {
    suspend fun execute(params: P): R
}
```

---

### 2. Модель параметров и результата
```kotlin
data class LoginParams(
    val email: String,
    val password: String
)

data class AuthResult(
    val token: String,
    val userId: String
)
```

---

### 3. Репозиторий
```kotlin
interface AuthRepository {
    suspend fun login(email: String, password: String): AuthResult
}
```

---

### 4. Реализация UseCase для авторизации
```kotlin
class LoginUseCase(
    private val authRepository: AuthRepository
) : UseCase<LoginParams, AuthResult> {

    override suspend fun execute(params: LoginParams): AuthResult {
        require(params.email.isNotBlank()) { "Email must not be blank" }
        require(params.password.isNotBlank()) { "Password must not be blank" }

        return authRepository.login(
            email = params.email.trim(),
            password = params.password
        )
    }
}
```

---

### 5. Использование
```kotlin
val loginUseCase = LoginUseCase(authRepository)

val result = loginUseCase.execute(
    LoginParams(
        email = "test@example.com",
        password = "123456"
    )
)

println("Token: ${result.token}, UserId: ${result.userId}")
```

---

### Если нужен вариант с обработкой ошибок
Можно возвращать `Result<AuthResult>`:

```kotlin
class LoginUseCase(
    private val authRepository: AuthRepository
) : UseCase<LoginParams, Result<AuthResult>> {

    override suspend fun execute(params: LoginParams): Result<AuthResult> {
        return runCatching {
            require(params.email.isNotBlank()) { "Email must not be blank" }
            require(params.password.isNotBlank()) { "Password must not be blank" }

            authRepository.login(
                email = params.email.trim(),
                password = params.password
            )
        }
    }
}
```

---

Если хочешь, я могу сразу написать **полный пример авторизации** с:
- `Retrofit`
- `DTO`
- `Repository`
- `UseCase`
- `ViewModel`
- `StateFlow`

в готовом рабочем виде.
```

### Attempt 2

```text
Ниже пример простой и удобной реализации `UseCase` для авторизации на Kotlin в стиле Clean Architecture.

### 1. Базовый `UseCase`
```kotlin
interface UseCase<in P, out R> {
    suspend operator fun invoke(params: P): R
}
```

---

### 2. Модель параметров и результата
```kotlin
data class LoginParams(
    val email: String,
    val password: String
)

data class AuthResult(
    val token: String,
    val userId: String
)
```

---

### 3. Репозиторий
```kotlin
interface AuthRepository {
    suspend fun login(email: String, password: String): AuthResult
}
```

---

### 4. Реализация UseCase для авторизации
```kotlin
class LoginUseCase(
    private val authRepository: AuthRepository
) : UseCase<LoginParams, AuthResult> {

    override suspend fun invoke(params: LoginParams): AuthResult {
        require(params.email.isNotBlank()) { "Email не должен быть пустым" }
        require(params.password.isNotBlank()) { "Пароль не должен быть пустым" }

        return authRepository.login(
            email = params.email,
            password = params.password
        )
    }
}
```

---

### 5. Пример использования
```kotlin
val loginUseCase = LoginUseCase(authRepository)

viewModelScope.launch {
    try {
        val result = loginUseCase(
            LoginParams(
                email = "test@mail.com",
                password = "123456"
            )
        )
        println("Token: ${result.token}")
    } catch (e: IllegalArgumentException) {
        println("Ошибка валидации: ${e.message}")
    } catch (e: Exception) {
        println("Ошибка авторизации: ${e.message}")
    }
}
```

---

### 6. Если нужен вариант с `Result`
Часто удобно возвращать `Result`, чтобы не кидать исключения напрямую:

```kotlin
class LoginUseCase(
    private val authRepository: AuthRepository
) {
    suspend operator fun invoke(params: LoginParams): Result<AuthResult> {
        return runCatching {
            require(params.email.isNotBlank()) { "Email не должен быть пустым" }
            require(params.password.isNotBlank()) { "Пароль не должен быть пустым" }
            authRepository.login(params.email, params.password)
        }
    }
}
```

Использование:
```kotlin
viewModelScope.launch {
    val result = loginUseCase(LoginParams("test@mail.com", "123456"))
    result.onSuccess { auth ->
        println("Success: ${auth.token}")
    }.onFailure { error ->
        println("Failure: ${error.message}")
    }
}
```

Если хочешь, я могу сразу написать **полный пример под Android + ViewModel + Repository + Retrofit + sealed class for UI state**.
```

### Attempt 3

```text
Ниже — простой и практичный пример `UseCase` для авторизации на Kotlin.  
Сделаю в стиле clean architecture: `UseCase` вызывает `Repository`, возвращает результат через `Result`.

## 1. Модель запроса и результата

```kotlin
data class LoginRequest(
    val email: String,
    val password: String
)

data class LoginResult(
    val token: String,
    val userId: String
)
```

## 2. Контракт репозитория

```kotlin
interface AuthRepository {
    suspend fun login(email: String, password: String): LoginResult
}
```

## 3. UseCase

```kotlin
class LoginUseCase(
    private val authRepository: AuthRepository
) {
    suspend operator fun invoke(email: String, password: String): Result<LoginResult> {
        return try {
            if (email.isBlank() || password.isBlank()) {
                Result.failure(IllegalArgumentException("Email и пароль не могут быть пустыми"))
            } else {
                val result = authRepository.login(email, password)
                Result.success(result)
            }
        } catch (e: Exception) {
            Result.failure(e)
        }
    }
}
```

## 4. Пример реализации репозитория

```kotlin
class AuthRepositoryImpl : AuthRepository {
    override suspend fun login(email: String, password: String): LoginResult {
        // Здесь обычно запрос в API
        if (email == "test@mail.com" && password == "123456") {
            return LoginResult(
                token = "mock_token_123",
                userId = "42"
            )
        } else {
            throw IllegalArgumentException("Неверный логин или пароль")
        }
    }
}
```

## 5. Использование

```kotlin
suspend fun authExample() {
    val repository = AuthRepositoryImpl()
    val useCase = LoginUseCase(repository)

    val result = useCase("test@mail.com", "123456")

    result
        .onSuccess {
            println("Успешный вход: token=${it.token}, userId=${it.userId}")
        }
        .onFailure {
            println("Ошибка авторизации: ${it.message}")
        }
}
```

## Если нужна более "чистая" архитектура

Можно сделать так, чтобы `UseCase` принимал один объект:

```kotlin
class LoginUseCase(
    private val authRepository: AuthRepository
) {
    suspend operator fun invoke(request: LoginRequest): Result<LoginResult> {
        return runCatching {
            require(request.email.isNotBlank()) { "Email не может быть пустым" }
            require(request.password.isNotBlank()) { "Пароль не может быть пустым" }

            authRepository.login(request.email, request.password)
        }
    }
}
```

Если хочешь, я могу ещё показать:
1. **UseCase с `sealed class` для состояния UI (`Loading/Success/Error`)**  
2. **полный пример под Android + MVVM + Hilt**  
3. **вариант с Retrofit и Kotlin Flow**
```

### Attempt 4

```text
Ниже — пример **UseCase для авторизации на Kotlin** в стиле clean architecture.  
Я покажу вариант с **coroutines**, **Result/sealed class**, и **repository abstraction**.

## 1. Модель результата

```kotlin
sealed class AuthResult {
    data class Success(val userId: String, val token: String) : AuthResult()
    data class Error(val message: String) : AuthResult()
}
```

## 2. Репозиторий

```kotlin
interface AuthRepository {
    suspend fun login(email: String, password: String): AuthResult
}
```

## 3. UseCase

```kotlin
class LoginUseCase(
    private val authRepository: AuthRepository
) {
    suspend operator fun invoke(email: String, password: String): AuthResult {
        if (email.isBlank()) {
            return AuthResult.Error("Email не может быть пустым")
        }
        if (password.isBlank()) {
            return AuthResult.Error("Пароль не может быть пустым")
        }

        return authRepository.login(email, password)
    }
}
```

## 4. Пример реализации репозитория

```kotlin
class AuthRepositoryImpl(
    private val authApi: AuthApi
) : AuthRepository {

    override suspend fun login(email: String, password: String): AuthResult {
        return try {
            val response = authApi.login(LoginRequest(email, password))
            if (response.isSuccessful && response.body() != null) {
                val body = response.body()!!
                AuthResult.Success(
                    userId = body.userId,
                    token = body.token
                )
            } else {
                AuthResult.Error(response.errorBody()?.string() ?: "Ошибка авторизации")
            }
        } catch (e: Exception) {
            AuthResult.Error(e.message ?: "Неизвестная ошибка")
        }
    }
}
```

## 5. DTO и API

```kotlin
data class LoginRequest(
    val email: String,
    val password: String
)

data class LoginResponse(
    val userId: String,
    val token: String
)

interface AuthApi {
    suspend fun login(request: LoginRequest): retrofit2.Response<LoginResponse>
}
```

## 6. Использование

```kotlin
viewModelScope.launch {
    when (val result = loginUseCase("test@mail.com", "123456")) {
        is AuthResult.Success -> {
            // сохранить токен, перейти дальше
        }
        is AuthResult.Error -> {
            // показать ошибку
        }
    }
}
```

---

Если хочешь, я могу сразу написать **полный пример под Android с MVVM, Retrofit, Repository, ViewModel и UseCase**, чтобы можно было вставить в проект.
```

### Attempt 5

```text
Конечно. Ниже пример **UseCase-класса для авторизации на Kotlin** в стиле clean architecture. Я покажу:

1. модель запроса/ответа,
2. интерфейс репозитория,
3. сам UseCase,
4. пример реализации вызова.

---

## 1) Модель данных

```kotlin
data class LoginRequest(
    val email: String,
    val password: String
)

data class LoginResult(
    val accessToken: String,
    val refreshToken: String? = null
)
```

---

## 2) Интерфейс репозитория

UseCase обычно не знает, как именно происходит авторизация — через сеть, БД и т.д. Он работает через абстракцию.

```kotlin
interface AuthRepository {
    suspend fun login(request: LoginRequest): LoginResult
}
```

---

## 3) UseCase для авторизации

### Вариант без параметров в конструкторе
```kotlin
class LoginUseCase(
    private val authRepository: AuthRepository
) {
    suspend operator fun invoke(email: String, password: String): Result<LoginResult> {
        return try {
            if (email.isBlank() || password.isBlank()) {
                return Result.failure(IllegalArgumentException("Email и password не должны быть пустыми"))
            }

            val result = authRepository.login(
                LoginRequest(
                    email = email.trim(),
                    password = password
                )
            )

            Result.success(result)
        } catch (e: Exception) {
            Result.failure(e)
        }
    }
}
```

---

## 4) Пример использования

```kotlin
class LoginViewModel(
    private val loginUseCase: LoginUseCase
) : ViewModel() {

    fun login(email: String, password: String) {
        viewModelScope.launch {
            val result = loginUseCase(email, password)

            result.onSuccess { authData ->
                // успех, сохраняем токен / переходим дальше
                println("Token: ${authData.accessToken}")
            }.onFailure { error ->
                // обработка ошибки
                println("Login error: ${error.message}")
            }
        }
    }
}
```

---

## 5) Если нужна более "чистая" версия с отдельным `Parameters`

Это более распространённый вариант в больших проектах:

```kotlin
class LoginUseCase(
    private val authRepository: AuthRepository
) {
    data class Params(
        val email: String,
        val password: String
    )

    suspend operator fun invoke(params: Params): Result<LoginResult> {
        return try {
            require(params.email.isNotBlank()) { "Email не должен быть пустым" }
            require(params.password.isNotBlank()) { "Password не должен быть пустым" }

            val result = authRepository.login(
                LoginRequest(
                    email = params.email.trim(),
                    password = params.password
                )
            )

            Result.success(result)
        } catch (e: Exception) {
            Result.failure(e)
        }
    }
}
```

Использование:

```kotlin
val result = loginUseCase(
    LoginUseCase.Params(
        email = "test@mail.com",
        password = "123456"
    )
)
```

---

## 6) Пример обработки доменных ошибок

Если хочешь сделать более правильно для архитектуры, можно вместо `Exception` использовать свои ошибки:

```kotlin
sealed class AuthError(message: String) : Throwable(message) {
    data class Validation(message: String) : AuthError(message)
    data class Network(message: String) : AuthError(message)
    data class Unknown(message: String) : AuthError(message)
}
```

И тогда UseCase:

```kotlin
class LoginUseCase(
    private val authRepository: AuthRepository
) {
    data class Params(
        val email: String,
        val password: String
    )

    suspend operator fun invoke(params: Params): Result<LoginResult> {
        if (params.email.isBlank()) {
            return Result.failure(AuthError.Validation("Email не должен быть пустым"))
        }
        if (params.password.isBlank()) {
            return Result.failure(AuthError.Validation("Пароль не должен быть пустым"))
        }

        return try {
            val result = authRepository.login(
                LoginRequest(
                    email = params.email.trim(),
                    password = params.password
                )
            )
            Result.success(result)
        } catch (e: java.io.IOException) {
            Result.failure(AuthError.Network("Нет подключения к сети"))
        } catch (e: Exception) {
            Result.failure(AuthError.Unknown("Неизвестная ошибка"))
        }
    }
}
```

---

Если хочешь, я могу сразу написать **полную реализацию авторизации** на Kotlin с:
- `Retrofit`,
- `Repository`,
- `UseCase`,
- `ViewModel`,
- `StateFlow`,
- и `sealed class UiState`.

Если нужно, скажи — и я соберу готовый пример проекта.
```
