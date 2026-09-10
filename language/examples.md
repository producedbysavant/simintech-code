# Примеры кода SimInTech

Все примеры используют синтаксис, корректный для кодогенерации в C (F9).

## 1. Усилитель с мёртвой зоной

```simintech
input u: double;
output y: double;
const
    deadzone = 0.5,
    gain = 2.0;

begin
    if abs(u) < deadzone then
        y = 0
    else
        y = (abs(u) - deadzone) * gain * sign(u);
end
```

## 2. Фильтр низких частот (апериодическое звено)

```simintech
input u: double;
output y: double;
const T = 0.5;    // постоянная времени
var state: double;

begin
    state = state + (u - state) * hmax / T;
    y = state;
end
```

## 3. Генератор синусоиды

```simintech
output y: double;
const
    omega = 2 * 3.14159 * 50, // 50 Гц
    amplitude = 5.0;

begin
    y = amplitude * sin(omega * time);
end
```

## 4. Релейный регулятор (двухпозиционный)

```simintech
input
    setpoint: double,
    measurement: double;
output control: double;
const hysteresis = 0.5;

begin
    if measurement < setpoint - hysteresis then
        control = 1  // включить нагрев
    else if measurement > setpoint + hysteresis then
        control = 0; // выключить нагрев
end
```

## 5. Скользящее среднее (фильтрация)

```simintech
input raw: double;
output filtered: double;
const N = 10;
var
    acc: double,
    idx: integer,
    scan: integer,
    buffer[N]: array;

begin
    // Кольцевой буфер: idx — номер последней записанной ячейки.
    // Переменные из var стартуют с нуля, поэтому первая запись идёт в buffer[1].
    idx = idx + 1;
    if idx > N then idx = 1;
    buffer[idx] = raw;

    acc = 0;
    for (scan = 1, N) do
        acc = acc + buffer[scan];
    filtered = acc / N;
end
```

> Накопитель назван `acc`, а не `sum`: `sum` — встроенная функция (см. `syntax.md`),
> и одноимённая переменная перекрывает её при трансляции в C. По той же причине
> счётчик цикла — `scan`, а не `i`: имена `i`, `j`, `c` занимает транслятор.

## 6. ПИ-регулятор скорости

```simintech
input
    speed_ref: double,
    speed_meas: double;
output torque_ref: double;
const
    Kp = 0.5,
    Ki = 10.0;
var
    error: double,
    integral: double;

begin
    error = speed_ref - speed_meas;
    integral = integral + error * hmax;
    torque_ref = Kp * error + Ki * integral;
end
```

## 7. Модель двигателя постоянного тока

```simintech
input
    voltage: double,
    load_torque: double;
output
    speed: double,
    current: double;
const
    R = 0.5, L = 0.01,   // сопротивление, индуктивность
    Ke = 0.1, Kt = 0.1,  // постоянные ЭДС и момента
    J = 0.01, B = 0.001; // момент инерции, вязкое трение
var
    state_current: double,
    state_speed: double;

begin
    state_current = state_current + (voltage - R*state_current - Ke*state_speed) * hmax / L;
    state_speed = state_speed + (Kt*state_current - load_torque - B*state_speed) * hmax / J;
    current = state_current;
    speed = state_speed;
end
```

## 8. Кусочно-линейная функция

```simintech
input x: double;
output y: double;
const
    x1 = 0, x2 = 5, x3 = 10,
    y1 = 0, y2 = 3, y3 = 3, y4 = 0;

begin
    if x <= x1 then
        y = y1
    else if x <= x2 then
        y = y1 + (y2 - y1) * (x - x1) / (x2 - x1)
    else if x <= x3 then
        y = y2 + (y3 - y2) * (x - x2) / (x3 - x2)
    else
        y = y4;
end
```

## 9. ШИМ-модулятор

```simintech
input duty_cycle: double;    // 0..1
output pwm: double;
const period = 0.001;        // период ШИМ
var cycle_time: double;

begin
    cycle_time = mod(time, period);
    if cycle_time < duty_cycle * period then
        pwm = 1
    else
        pwm = 0;
end
```

## 10. Квадратурный генератор (sin + cos)

```simintech
output
    sine: double,
    cosine: double;
const omega = 2 * 3.14159 * 1.0; // 1 Гц
var phase: double;

begin
    phase = phase + omega * hmax;
    if phase > 2 * 3.14159 then
        phase = phase - 2 * 3.14159;
    sine = sin(phase);
    cosine = cos(phase);
end
```

## Бонус: Гирлянда на выходные

```simintech
output y: double;
const N = 8;
var
    idx: integer,
    acc: double;

begin
    acc = 0;
    for (idx = 1, N) do
        acc = acc + sin(idx * time) / idx;
    y = acc;
end
```
