# Туториал 2: Переменные и типы данных

Разбираемся с типами данных, переменными и областями видимости во встроенном языке SimInTech.
Канонический синтаксис языка — в `language/syntax.md`.

## Что ты узнаешь

- Какие типы данных поддерживает SimInTech
- Как объявлять и инициализировать переменные
- Что такое область видимости
- Как работают массивы (и почему индексация начинается с 1)

## Типы данных

SimInTech различает скалярные типы, массивы и строки:

| Тип | Описание | Кодогенерация в C |
|-----|----------|-------------------|
| `double` | Вещественное число (64 бит) | да |
| `integer` | Целое число | да |
| `boolean` | Логическое значение (`true`/`false`) | да |
| `array` | Массив вещественных чисел | да (только статический) |
| `intarray` | Массив целых чисел | да (только статический) |
| `string` | Строка | нет |

Объявления **плоские** и идут до тела расчёта. Каждая переменная указывается
со своим типом:

```simintech
const MAX = 100;

var
    count: integer,
    temperature: double,
    isReady: boolean,
    R[MAX]: array;
```

Группировать имена под одним типом нельзя:

```simintech
// НЕПРАВИЛЬНО:
var a, b, c: double;
```

> `string` работает в интерпретаторе, но **не кодогенерируется в C**. Если проект
> должен проходить F9 (кодогенерацию), строки в блоке использовать нельзя — храни
> числовые коды или выводи диагностику через сигналы (см. `language/pitfalls.md`).

## Практика: блок с различными типами

Создадим блок, который использует несколько типов данных. Строк здесь нет —
только кодогенерируемые типы:

```simintech
input
    analogInput: double,
    digitalInput: boolean;
output
    analogOutput: double,
    digitalOutput: boolean;
const limit = 100.0;

var
    counter: integer,
    acc: double,
    average: double,
    limitReached: boolean;

begin
    // Счётчик активных шагов
    if digitalInput = true then
        counter = counter + 1;

    // Накопление суммы
    acc = acc + analogInput;

    // Среднее значение (защита от деления на ноль)
    if counter > 0 then
        average = acc / counter
    else
        average = 0.0;

    // Логика: если среднее превысило порог
    if average > limit then
        limitReached = true
    else
        limitReached = false;

    // Выходы
    analogOutput = average;
    digitalOutput = limitReached;
end;
```

Здесь нет ни `var:`, ни `function`, ни `end_if` — тело обрамляется парой
`begin ... end`, а условия закрываются `end;` (см. `language/syntax.md`).

## Преобразование типов

### Управляемое округление

Отдельных функций-приведений (`int(...)`, `double(...)`) в языке нет — числовые
значения преобразуются автоматически, а для управляемого округления есть
`round`, `floor`, `ceil`:

```simintech
var
    x: double,
    n: integer,
    s: string;

begin
    x = 3.14159;
    n = round(x);       // 3 — округление до ближайшего целого
    n = floor(x);       // 3 — округление вниз
    n = ceil(x);        // 4 — округление вверх
    s = floattostr(x);  // "3.14159" (только интерпретатор: string не кодогенерируется)
end;
```

Функции `rtoa`/`ator`/`atoi`/`itoa` из ранних версий этого туториала в
справочнике языка отсутствуют. Из строковых операций документированы
`strcopy`, `pos`, `lowercase`, `floattostr`, но все они непригодны для
кодогенерации.

### Неявное преобразование

Числовое преобразование между `integer` и `double` выполняется автоматически:

```simintech
var
    n: integer,
    d: double;

begin
    n = 5;
    d = n;          // неявно: d = 5.0
    d = d / 2.0;    // 2.5
    n = round(d);   // обратно к целому — округление явное
end;
```

## Массивы

### Одномерные массивы

Массивы объявляются **только со статическим размером** и индексируются
**от 1**, а не от 0. Размер задаётся константой или литералом:

```simintech
const NREAD = 10;

var
    readings[NREAD]: array,
    values[4]: array,
    idx: integer,
    acc: double;

begin
    // Инициализация массива: индексы 1..NREAD
    for (idx = 1, NREAD) do
        readings[idx] = 0.0;

    // Использование
    values[1] = 10.0;                 // ПЕРВЫЙ элемент
    values[2] = 20.0;                 // ВТОРОЙ элемент
    acc = values[1] + values[2];      // 30.0
    readings[5] = acc;                // пятый элемент

    // Обход всего массива
    for (idx = 1, NREAD) do
        readings[idx] = idx * 1.0;
end;
```

Инициализаторы-списки вида `{1.0, 2.0, 3.0}` и прямое присваивание массивов
(`A = B`) не транслируются в C — заполняйте массивы поэлементно в цикле.

### Двумерные массивы (матрицы)

Размерности перечисляются через запятую, доступ — тоже:

```simintech
const NROW = 3, NCOL = 3;

var
    matrix[NROW, NCOL]: array,
    row: integer,
    col: integer,
    acc: double;

begin
    // Единичная матрица
    for (row = 1, NROW) do
        for (col = 1, NCOL) do
            if row = col then
                matrix[row, col] = 1.0
            else
                matrix[row, col] = 0.0;

    // Сумма всех элементов
    acc = 0.0;
    for (row = 1, NROW) do
        for (col = 1, NCOL) do
            acc = acc + matrix[row, col];
end;
```

Матричные операции (`*`, `\`, `./`) не кодогенерируются. Умножение матриц,
транспонирование и т.п. реализуй вложенными циклами — пример есть в
`patterns/state-space.md`.

## Область видимости

### Локальные переменные блока

Переменные из секции `var` видны только внутри своего блока. Всё, чем блок
обменивается с другими блоками, объявляется как `input`/`output`:

```simintech
input u: double;
output y: double;
var scale: double;

begin
    scale = 2.0;   // локальная — снаружи недоступна
    y = u * scale;
end;
```

### Глобальные константы проекта

Общие настройки выносятся в константы проекта: они объявляются в скрипте
проекта (см. `language/keywords.md`). Внутри блока не используй префикс `::` —
такого синтаксиса в языке нет; надёжнее передать значение через входной порт
или объявить `const` прямо в блоке.

### Статические переменные

Все переменные из `var` сохраняют значение между шагами расчёта. Отдельного
слова для «статической» переменной не нужно:

```simintech
output count: integer;
var internalCount: integer;

begin
    internalCount = internalCount + 1;  // сохраняется между шагами
    count = internalCount;
end;
```

## Практическое задание

Создай блок, который:
1. Принимает 3 аналоговых входа
2. Вычисляет их среднее, минимум и максимум
3. Хранит историю последних 10 значений
4. Выдаёт `true`, если среднее за 10 шагов превышает порог

```simintech
input
    ch1: double,
    ch2: double,
    ch3: double;
output
    average: double,
    minimum: double,
    maximum: double,
    alarm: boolean;
const
    HIST = 10,
    threshold = 50.0;
var
    history[HIST]: array,
    index: integer,
    scan: integer,
    acc: double;

begin
    // Текущие значения
    average = (ch1 + ch2 + ch3) / 3.0;
    minimum = min(min(ch1, ch2), ch3);
    maximum = max(max(ch1, ch2), ch3);

    // Кольцевой буфер: index — номер последней записанной ячейки (1..HIST)
    index = index + 1;
    if index > HIST then
        index = 1;
    history[index] = average;

    // Среднее по всей истории
    acc = 0.0;
    for (scan = 1, HIST) do
        acc = acc + history[scan];

    // Сигнализация
    if acc / HIST > threshold then
        alarm = true
    else
        alarm = false;
end;
```

> Накопитель назван `acc`, а счётчик — `scan`: имя `sum` совпадает со встроенной
> функцией, а имена `i`, `j`, `c` занимает транслятор C (см. `language/pitfalls.md`).

## Проверь себя

1. Какой тип данных выберешь для хранения денежной суммы? → `double` (или целое число копеек в `integer`)
2. Как округлить `3.14` до целого? → `round(3.14)`; вниз — `floor`, вверх — `ceil`
3. Как обратиться к третьему элементу массива `arr`? → `arr[3]` (индексация с 1)
4. Сохраняется ли значение переменной между шагами? → Да, если она объявлена в `var`

## Типичные ошибки

```simintech
// Ошибка 1: выход за границы массива
const N = 5;
var arr[N]: array;

begin
    arr[5] = 1.0;   // ПРАВИЛЬНО: последний допустимый индекс — N = 5
    arr[6] = 1.0;   // ОШИБКА: индекс 6 вне диапазона [1..5]
end;
```

```simintech
// Ошибка 2: имена i, j, c конфликтуют с счётчиками транслятора
var i: integer;   // НЕДОПУСТИМО

begin
    for (i = 1, 10) do   // ошибка компиляции C
        y = y + 1;
end;
```

```simintech
// Ошибка 3: расчёт на «обнуление» переменной на каждом шаге
output y: double;
var acc: double;

begin
    // acc НЕ сбрасывается сам — значение живёт между шагами.
    // Если нужна сумма за один шаг, обнуляй явно:
    acc = 0.0;
    acc = acc + 1.0;
    y = acc;
end;
```

```simintech
// Ошибка 4: C-подобные операторы и not
// if (x == 0) { ... }   — неверно
// if not flag then ...  — not не поддерживается
if x = 0 then begin y = 1.0; end;
if flag = false then begin y = 0.0; end;
```

## Что дальше?

Теперь ты знаешь всё о переменных и типах. Переходи к туториалу 3:
«Субмодели: создаём макроблоки»
