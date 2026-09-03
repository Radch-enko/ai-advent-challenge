# Temperature experiment

- Model: `gpt-5.4-mini`
- Runs per temperature: 5
- Created: 2026-09-03T22:31:25+06:00

## Prompt

```text
Сгенерируй код валидации поля ввода email адреса
```

## Summary

| Temperature | Completed runs | Avg chars | Avg words | Avg output tokens | Avg unique-word ratio | Avg pairwise similarity |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 0 | 5 | 1496.2 | 169.4 | 425.8 | 0.522 | 0.410 |
| 0.7 | 5 | 1436.6 | 158.4 | 400.0 | 0.526 | 0.321 |
| 1.7 | 5 | 1236.2 | 138.0 | 332.6 | 0.570 | 0.415 |

Lower pairwise similarity means the answers are more lexically different. It does not measure semantic quality or correctness.

## Temperature 0

| Attempt | Chars | Words | Lines | Output tokens | Reasoning tokens | Unique-word ratio |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 1333 | 158 | 51 | 387.0 | 0.0 | 0.551 |
| 2 | 1397 | 163 | 54 | 399.0 | 0.0 | 0.528 |
| 3 | 1203 | 139 | 45 | 337.0 | 0.0 | 0.604 |
| 4 | 2121 | 234 | 90 | 605.0 | 0.0 | 0.457 |
| 5 | 1427 | 153 | 55 | 401.0 | 0.0 | 0.471 |

### Attempt 1

```text
Конечно. Ниже несколько вариантов валидации email — от простого до более практичного.

### 1. Простая валидация на JavaScript
```javascript
function validateEmail(email) {
  const regex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
  return regex.test(email);
}

// Пример
console.log(validateEmail("test@example.com")); // true
console.log(validateEmail("invalid-email"));     // false
```

### 2. Валидация поля ввода в HTML + JS
```html
<input type="email" id="email" placeholder="Введите email">
<button onclick="checkEmail()">Проверить</button>
<p id="result"></p>

<script>
  function checkEmail() {
    const email = document.getElementById("email").value;
    const result = document.getElementById("result");

    const regex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

    if (regex.test(email)) {
      result.textContent = "Email корректен";
      result.style.color = "green";
    } else {
      result.textContent = "Некорректный email";
      result.style.color = "red";
    }
  }
</script>
```

### 3. Более строгая функция
```javascript
function validateEmail(email) {
  const regex = /^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$/;
  return regex.test(email);
}
```

Если хочешь, я могу сразу сгенерировать:
- **валидацию для React**
- **валидацию для Vue**
- **валидацию на TypeScript**
- **валидацию с сообщением об ошибке под полем**
```

### Attempt 2

```text
Конечно. Ниже несколько вариантов валидации email — от простого до более практичного.

### 1. Простая валидация на JavaScript
```javascript
function validateEmail(email) {
  const regex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
  return regex.test(email);
}

// Пример
console.log(validateEmail("test@example.com")); // true
console.log(validateEmail("invalid-email"));     // false
```

### 2. Валидация поля ввода в HTML + JS
```html
<input type="email" id="email" placeholder="Введите email">
<button onclick="checkEmail()">Проверить</button>
<p id="result"></p>

<script>
  function validateEmail(email) {
    const regex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    return regex.test(email);
  }

  function checkEmail() {
    const email = document.getElementById("email").value;
    const result = document.getElementById("result");

    if (validateEmail(email)) {
      result.textContent = "Email корректный";
      result.style.color = "green";
    } else {
      result.textContent = "Email некорректный";
      result.style.color = "red";
    }
  }
</script>
```

### 3. Более строгая проверка
```javascript
function validateEmail(email) {
  const regex = /^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$/;
  return regex.test(email);
}
```

Если хочешь, я могу сразу сделать:
- **валидацию для React**
- **валидацию для Vue**
- **валидацию с подсветкой ошибки под полем**
- **валидацию на TypeScript**
```

### Attempt 3

```text
Конечно. Ниже — простой и практичный пример валидации email-поля на JavaScript.

### HTML
```html
<form id="signupForm">
  <label for="email">Email:</label>
  <input type="text" id="email" name="email" />
  <div id="emailError" style="color: red;"></div>
  <button type="submit">Отправить</button>
</form>
```

### JavaScript
```javascript
const form = document.getElementById('signupForm');
const emailInput = document.getElementById('email');
const emailError = document.getElementById('emailError');

function validateEmail(email) {
  const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
  return emailRegex.test(email);
}

form.addEventListener('submit', function (event) {
  const email = emailInput.value.trim();

  if (!validateEmail(email)) {
    event.preventDefault();
    emailError.textContent = 'Введите корректный email адрес.';
  } else {
    emailError.textContent = '';
  }
});
```

### Что делает код
- Проверяет, что email не пустой
- Убеждается, что есть `@` и доменная часть
- Показывает сообщение об ошибке, если формат неверный

Если хочешь, я могу сразу сделать:
1. **валидацию на React**
2. **валидацию на Vue**
3. **валидацию с подсветкой поля**
4. **более строгую проверку email**
```

### Attempt 4

```text
Конечно. Ниже несколько вариантов валидации email — от простого к более практичному.

### 1. JavaScript: простая функция валидации
```js
function validateEmail(email) {
  const regex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
  return regex.test(email);
}

// Пример:
console.log(validateEmail("test@example.com")); // true
console.log(validateEmail("bad-email"));        // false
```

### 2. HTML + JavaScript для поля ввода
```html
<input type="email" id="email" placeholder="Введите email">
<button onclick="checkEmail()">Проверить</button>
<p id="result"></p>

<script>
  function checkEmail() {
    const email = document.getElementById("email").value;
    const result = document.getElementById("result");

    const regex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

    if (regex.test(email)) {
      result.textContent = "Email корректный";
      result.style.color = "green";
    } else {
      result.textContent = "Email некорректный";
      result.style.color = "red";
    }
  }
</script>
```

### 3. Более строгая проверка
Если нужна чуть более надежная проверка:
```js
function validateEmail(email) {
  const regex = /^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$/;
  return regex.test(email);
}
```

### 4. Валидация в React
```jsx
import { useState } from "react";

export default function EmailInput() {
  const [email, setEmail] = useState("");
  const [error, setError] = useState("");

  const validateEmail = (value) => {
    const regex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    return regex.test(value);
  };

  const handleChange = (e) => {
    const value = e.target.value;
    setEmail(value);

    if (value && !validateEmail(value)) {
      setError("Введите корректный email");
    } else {
      setError("");
    }
  };

  return (
    <div>
      <input
        type="email"
        value={email}
        onChange={handleChange}
        placeholder="Email"
      />
      {error && <p style={{ color: "red" }}>{error}</p>}
    </div>
  );
}
```

Если хочешь, я могу сразу сгенерировать:
- **валидацию для Vue**
- **валидацию для Angular**
- **валидацию на TypeScript**
- **валидацию с подсветкой ошибки под полем**
```

### Attempt 5

```text
Конечно. Ниже несколько вариантов валидации email — от простого к более практичному.

### 1. Простая валидация на JavaScript
```html
<input type="text" id="email" placeholder="Введите email">
<button onclick="validateEmail()">Проверить</button>

<script>
  function validateEmail() {
    const email = document.getElementById('email').value.trim();
    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

    if (emailRegex.test(email)) {
      alert('Email корректен');
    } else {
      alert('Некорректный email');
    }
  }
</script>
```

### 2. Валидация при вводе
```html
<input type="text" id="email" placeholder="Введите email">
<div id="error" style="color:red;"></div>

<script>
  const emailInput = document.getElementById('email');
  const error = document.getElementById('error');

  emailInput.addEventListener('input', () => {
    const email = emailInput.value.trim();
    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

    if (email === '') {
      error.textContent = '';
    } else if (!emailRegex.test(email)) {
      error.textContent = 'Введите корректный email';
    } else {
      error.textContent = '';
    }
  });
</script>
```

### 3. HTML5-валидация
```html
<input type="email" id="email" placeholder="Введите email" required>
```

Если хочешь, я могу сразу сгенерировать:
- **валидацию на React**
- **валидацию на Vue**
- **валидацию на TypeScript**
- **валидацию с подсветкой ошибки под полем**
```

## Temperature 0.7

| Attempt | Chars | Words | Lines | Output tokens | Reasoning tokens | Unique-word ratio |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 1613 | 180 | 63 | 454.0 | 0.0 | 0.483 |
| 2 | 1458 | 151 | 63 | 395.0 | 0.0 | 0.477 |
| 3 | 1261 | 145 | 48 | 347.0 | 0.0 | 0.607 |
| 4 | 2045 | 226 | 85 | 581.0 | 0.0 | 0.473 |
| 5 | 806 | 90 | 32 | 223.0 | 0.0 | 0.589 |

### Attempt 1

```text
Конечно. Вот простой и практичный пример валидации email для JavaScript.

### Вариант 1: функция валидации
```js
function validateEmail(email) {
  const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
  return emailRegex.test(email);
}

// Примеры
console.log(validateEmail("test@example.com")); // true
console.log(validateEmail("wrong-email"));      // false
```

### Вариант 2: валидация поля ввода HTML
```html
<input type="email" id="emailInput" placeholder="Введите email">
<button onclick="checkEmail()">Проверить</button>
<p id="result"></p>

<script>
  function validateEmail(email) {
    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    return emailRegex.test(email);
  }

  function checkEmail() {
    const email = document.getElementById("emailInput").value;
    const result = document.getElementById("result");

    if (validateEmail(email)) {
      result.textContent = "Email корректный";
      result.style.color = "green";
    } else {
      result.textContent = "Email некорректный";
      result.style.color = "red";
    }
  }
</script>
```

### Вариант 3: строгая проверка с сообщением об ошибке
```js
function validateEmail(email) {
  if (!email) return "Email обязателен";
  const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
  if (!emailRegex.test(email)) return "Введите корректный email";
  return null;
}

const error = validateEmail("user@mail.com");
if (error) {
  console.log(error);
} else {
  console.log("OK");
}
```

Если хочешь, я могу сразу сгенерировать:
- **валидацию на React**
- **валидацию на Vue**
- **валидацию на TypeScript**
- **валидацию с подсветкой ошибки под полем**
```

### Attempt 2

```text
Ниже пример простой валидации поля email на JavaScript.

### HTML
```html
<form id="emailForm">
  <label for="email">Email:</label>
  <input type="text" id="email" name="email" />
  <button type="submit">Отправить</button>
  <p id="emailError" style="color: red;"></p>
</form>
```

### JavaScript
```javascript
const form = document.getElementById('emailForm');
const emailInput = document.getElementById('email');
const emailError = document.getElementById('emailError');

function validateEmail(email) {
  // Простая проверка email
  const regex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
  return regex.test(email);
}

form.addEventListener('submit', function (event) {
  event.preventDefault();

  const email = emailInput.value.trim();

  if (!validateEmail(email)) {
    emailError.textContent = 'Введите корректный email адрес';
    emailInput.focus();
  } else {
    emailError.textContent = '';
    alert('Email валиден!');
    // Здесь можно отправить форму
  }
});
```

### Вариант для live-валидации
```javascript
emailInput.addEventListener('input', function () {
  const email = emailInput.value.trim();

  if (email === '') {
    emailError.textContent = '';
    return;
  }

  if (!validateEmail(email)) {
    emailError.textContent = 'Некорректный email';
  } else {
    emailError.textContent = '';
  }
});
```

Если хочешь, я могу сразу дать:
- **валидацию на React**
- **валидацию на Vue**
- **TypeScript-версию**
- **более строгий regex для email**
```

### Attempt 3

```text
Вот простой пример валидации поля ввода email на JavaScript.

### HTML
```html
<form id="emailForm">
  <label for="email">Email:</label>
  <input type="text" id="email" name="email" placeholder="name@example.com" />
  <button type="submit">Отправить</button>
  <div id="emailError" style="color: red;"></div>
</form>
```

### JavaScript
```javascript
const form = document.getElementById('emailForm');
const emailInput = document.getElementById('email');
const emailError = document.getElementById('emailError');

form.addEventListener('submit', function (e) {
  e.preventDefault();

  const email = emailInput.value.trim();
  const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

  if (!email) {
    emailError.textContent = 'Введите email адрес';
    return;
  }

  if (!emailRegex.test(email)) {
    emailError.textContent = 'Введите корректный email адрес';
    return;
  }

  emailError.textContent = '';
  alert('Email корректен!');
});
```

### Как это работает
- Проверяет, что поле не пустое.
- Проверяет формат email через регулярное выражение.
- Показывает сообщение об ошибке, если email некорректен.

Если хочешь, я могу сразу дать:
1. **вариант на React**,  
2. **вариант с валидацией в реальном времени**,  
3. **более строгую regex-проверку email**.
```

### Attempt 4

```text
Конечно. Ниже несколько вариантов валидации email — от простого к более практичному.

### 1. JavaScript: простая функция валидации
```js
function isValidEmail(email) {
  const regex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
  return regex.test(email);
}

// Пример:
console.log(isValidEmail("test@example.com")); // true
console.log(isValidEmail("bad-email"));        // false
```

### 2. HTML + JavaScript для поля ввода
```html
<input type="text" id="email" placeholder="Введите email">
<button onclick="validateEmail()">Проверить</button>
<p id="result"></p>

<script>
  function validateEmail() {
    const email = document.getElementById("email").value;
    const result = document.getElementById("result");

    const regex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

    if (regex.test(email)) {
      result.textContent = "Email корректный";
      result.style.color = "green";
    } else {
      result.textContent = "Некорректный email";
      result.style.color = "red";
    }
  }
</script>
```

### 3. Более строгая проверка в JavaScript
```js
function isValidEmail(email) {
  const regex = /^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$/;
  return regex.test(email);
}
```

### 4. Если нужен React
```jsx
import { useState } from "react";

export default function EmailInput() {
  const [email, setEmail] = useState("");
  const [error, setError] = useState("");

  const validate = (value) => {
    const regex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    if (!regex.test(value)) {
      setError("Введите корректный email");
    } else {
      setError("");
    }
  };

  return (
    <div>
      <input
        type="email"
        value={email}
        onChange={(e) => {
          setEmail(e.target.value);
          validate(e.target.value);
        }}
        placeholder="Email"
      />
      {error && <p style={{ color: "red" }}>{error}</p>}
    </div>
  );
}
```

Если хочешь, я могу сразу написать:
- **валидацию для React / Vue / Angular**
- **валидацию с подсветкой ошибки**
- **валидацию на TypeScript**
- **проверку email по требованиям RFC**
```

### Attempt 5

```text
Ниже пример простой валидации email на JavaScript.

### HTML
```html
<input type="text" id="email" placeholder="Введите email">
<button onclick="validateEmail()">Проверить</button>
<p id="result"></p>
```

### JavaScript
```javascript
function validateEmail() {
  const email = document.getElementById('email').value.trim();
  const result = document.getElementById('result');

  const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

  if (emailRegex.test(email)) {
    result.textContent = 'Email корректный';
    result.style.color = 'green';
  } else {
    result.textContent = 'Введите корректный email';
    result.style.color = 'red';
  }
}
```

Если хочешь, могу сразу дать:
- **валидацию на React**
- **валидацию на Vue**
- **валидацию с подсветкой ошибки под полем**
- **более строгую проверку email**
```

## Temperature 1.7

| Attempt | Chars | Words | Lines | Output tokens | Reasoning tokens | Unique-word ratio |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 1855 | 205 | 64 | 506.0 | 0.0 | 0.459 |
| 2 | 1066 | 126 | 42 | 297.0 | 0.0 | 0.643 |
| 3 | 1073 | 130 | 42 | 292.0 | 0.0 | 0.646 |
| 4 | 1290 | 130 | 44 | 329.0 | 0.0 | 0.515 |
| 5 | 897 | 99 | 34 | 239.0 | 0.0 | 0.586 |

### Attempt 1

```text
Вот простой и практичный код валидации email-поля на JavaScript.

### HTML + JavaScript
```html
<form id="signupForm">
  <label for="email">Email:</label>
  <input type="text" id="email" name="email" />
  <button type="submit">Отправить</button>
  <div id="emailError" style="color:red; margin-top:8px;"></div>
</form>

<script>
  const form = document.getElementById("signupForm");
  const emailInput = document.getElementById("email");
  const emailError = document.getElementById("emailError");

  function validateEmail(email) {
    const regex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    return regex.test(email);
  }

  form.addEventListener("submit", function (event) {
    const email = emailInput.value.trim();

    if (!validateEmail(email)) {
      event.preventDefault();
      emailError.textContent = "Введите корректный email адрес.";
      emailInput.style.borderColor = "red";
    } else {
      emailError.textContent = "";
      emailInput.style.borderColor = "";
    }
  });
</script>
```

### Что делает код
- Проверяет, что поле не пустое
- Проверяет формат email с помощью регулярного выражения
- Показывает сообщение об ошибке, если email некорректный

### Если нужен вариант только для `input`-валидации в реальном времени:
```html
<input type="text" id="email" placeholder="Введите email" />
<div id="error" style="color:red;"></div>

<script>
  const email = document.getElementById("email");
  const error = document.getElementById("error");

  email.addEventListener("input", () => {
    const value = email.value.trim();
    const isValid = /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value);

    error.textContent = value && !isValid ? "Некорректный email" : "";
  });
</script>
```

Если хочешь, я могу сразу сгенерировать:
- валидацию **на React**
- валидацию **на Vue**
- валидацию **с HTML5 + pattern**
- **более строгую** проверку email
```

### Attempt 2

```text
Вот простой и практичный вариант валидации email-адреса на JavaScript.

### HTML
```html
<label for="email">Email:</label>
<input type="email" id="email" name="email" />
<button onclick="validateEmail()">Проверить</button>

<p id="result"></p>
```

### JavaScript
```javascript
function validateEmail() {
  const emailInput = document.getElementById('email');
  const result = document.getElementById('result');
  const email = emailInput.value.trim();

  // Простая проверка на корректный формат email
  const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

  if (emailRegex.test(email)) {
    result.textContent = 'Email введён корректно';
    result.style.color = 'green';
  } else {
    result.textContent = 'Некорректный email';
    result.style.color = 'red';
  }
}
```

### Что проверяет регулярка:
- наличие символа `@`
- наличие доменной части
- наличие точки в домене
- отсутствие пробелов

Если хочешь, я могу сразу сделать:
1. **валидацию на React**
2. **валидацию на Vue**
3. **валидацию с выводом ошибки под полем**
4. **более строгую регулярку для email**
```

### Attempt 3

```text
Ниже простой и практичный пример валидации email поля на JavaScript.

### HTML
```html
<input type="email" id="email" placeholder="Введите email">
<button onclick="validateEmail()">Проверить</button>
<p id="error" style="color:red;"></p>
```

### JavaScript
```javascript
function validateEmail() {
  const emailInput = document.getElementById('email');
  const error = document.getElementById('error');
  const email = emailInput.value.trim();

  const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

  if (email === '') {
    error.textContent = 'Email не может быть пустым';
    return false;
  }

  if (!emailRegex.test(email)) {
    error.textContent = 'Введите корректный email адрес';
    return false;
  }

  error.textContent = 'Email корректен';
  return true;
}
```

### Что делает код
- Проверяет, что поле не пустое
- Проверяет формат email с помощью регулярного выражения
- Показывает сообщение об ошибке или успехе

Если хочешь, я могу сразу дать:
1. **вариант для React**
2. **вариант с валидацией на вводе без кнопки**
3. **более строгую regex-проверку email**
```

### Attempt 4

```text
Вот простой и практичный пример валидации email-поля на JavaScript:

```html
<form id="loginForm">
  <label for="email">Email:</label>
  <input type="text" id="email" name="email" />
  <button type="submit">Отправить</button>
  <div id="emailError" style="color: red;"></div>
</form>

<script>
  const form = document.getElementById('loginForm');
  const emailInput = document.getElementById('email');
  const emailError = document.getElementById('emailError');

  function validateEmail(email) {
    // Базовая проверка формата email
    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    return emailRegex.test(email);
  }

  form.addEventListener('submit', function (event) {
    const email = emailInput.value.trim();

    if (!validateEmail(email)) {
      event.preventDefault();
      emailError.textContent = 'Введите корректный email адрес';
      emailInput.style.borderColor = 'red';
    } else {
      emailError.textContent = '';
      emailInput.style.borderColor = '';
    }
  });

  emailInput.addEventListener('input', function () {
    if (emailError.textContent) {
      emailError.textContent = '';
      emailInput.style.borderColor = '';
    }
  });
</script>
```

Если нужен более строгий вариант валидации или пример для React / Vue / Angular — могу сразу сделать.
```

### Attempt 5

```text
Вот простой пример валидации email в JavaScript:

```html
<input type="text" id="email" placeholder="Введите email">
<div id="error" style="color:red;"></div>

<script>
  const input = document.getElementById('email');
  const error = document.getElementById('error');

  function validateEmail(value) {
    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    return emailRegex.test(value);
  }

  input.addEventListener('input', () => {
    const value = input.value.trim();

    if (value === "") {
      error.textContent = "Поле email не может быть пустым";
    } else if (!validateEmail(value)) {
      error.textContent = "Введите корректный email";
    } else {
      error.textContent = "";
    }
  });
</script>
```

Если нужно, могу также сгенерировать:
- валидацию на **React**
- валидацию на **TypeScript**
- вариант с **Formik / React Hook Form**
- вариант на **PHP / Python / Java**
```
