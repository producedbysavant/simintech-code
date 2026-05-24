# Ключевые слова SimInTech

## `const` — Константа

Значение задаётся один раз, не меняется во время расчёта.

```c
const g = 9.81;
const pi = 3.1415926535;
const N = 100;
const tau = 0.5;
const A[2,2] = [-2, 1; 0, -3];
```

## `var` — Алгебраическая переменная

Создаётся заново на каждом шаге. Значение из предыдущего шага НЕ сохраняется.

```c
var x, y, z;
var temp = 25.0;
var result[10];
var matrix[3, 3];

// Присваивание каждый шаг
x = u * 2.0;
result[i] = sin(t * omega);
```

## `init` — Динамическая переменная

Сохраняет значение между шагами. Используется для интеграторов, счётчиков, накопления.

```c
init counter = 0;
init integral = 0.0;
init state[5] = [0, 0, 0, 0, 0];

counter = counter + 1;
integral = integral + error * h;
state[0] = state[0] + derivative * h;
```

## `input` — Вход порта

Читает значение из входного порта блока.

```c
input u;           // один скалярный вход
input u[3];        // векторный вход (3 элемента)
input u, v, w;     // три скалярных входа
```

## `output` — Выход порта

Записывает значение в выходной порт блока.

```c
output y;
output y[3];
output y1, y2;
y = u * Kp;
```

## Примеры комбинаций

```c
// Усилитель с ограничением
input u;
output y;
const K = 2.5;
const y_max = 10.0;
var y_raw;

y_raw = u * K;
if (y_raw > y_max) {
    y = y_max;
} else if (y_raw < -y_max) {
    y = -y_max;
} else {
    y = y_raw;
}
```

```c
// Интегратор с насыщением
input u;
output y;
const dt = 0.01;
const y_max = 100.0;
init y = 0;

y = y + u * dt;
if (y > y_max) {
    y = y_max;
} else if (y < -y_max) {
    y = -y_max;
}
```
