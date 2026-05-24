# Примеры кода SimInTech

## 1. Усилитель с мёртвой зоной

```c
input u;
output y;
const deadzone = 0.5;
const gain = 2.0;

if (abs(u) < deadzone) {
    y = 0;
} else {
    y = (abs(u) - deadzone) * gain * sign(u);
}
```

## 2. Фильтр низких частот (апериодическое звено)

```c
input u;
output y;
const T = 0.5;    // постоянная времени
init y = 0;

y = y + (u - y) * h / T;
```

## 3. Генератор синусоиды

```c
output y;
const omega = 2 * 3.14159 * 50; // 50 Гц
const amplitude = 5.0;

y = amplitude * sin(omega * t);
```

## 4. Релейный регулятор (двухпозиционный)

```c
input setpoint, measurement;
output control;
const hysteresis = 0.5;

if (measurement < setpoint - hysteresis) {
    control = 1;  // включить нагрев
} else if (measurement > setpoint + hysteresis) {
    control = 0;  // выключить нагрев
}
```

## 5. Скользящее среднее (фильтрация)

```c
input raw;
output filtered;
const N = 10;
var sum, i;
init buffer[10] = [0,0,0,0,0,0,0,0,0,0];
init idx = 0;

buffer[idx] = raw;
idx = idx + 1;
if (idx >= N) { idx = 0; }

sum = 0;
for (i = 0; i < N; i++) {
    sum = sum + buffer[i];
}
filtered = sum / N;
```

## 6. ПИ-регулятор скорости

```c
input speed_ref, speed_meas;
output torque_ref;
const Kp = 0.5, Ki = 10.0;
var error;
init integral = 0;

error = speed_ref - speed_meas;
integral = integral + error * h;
torque_ref = Kp * error + Ki * integral;
```

## 7. Модель двигателя постоянного тока

```c
input voltage, load_torque;
output speed, current;
const R = 0.5, L = 0.01;  // сопротивление, индуктивность
const Ke = 0.1, Kt = 0.1; // постоянные ЭДС и момента
const J = 0.01, B = 0.001; // момент инерции, вязкое трение
init current = 0;
init speed = 0;

current = current + (voltage - R*current - Ke*speed) * h / L;
speed = speed + (Kt*current - load_torque - B*speed) * h / J;
```

## 8. Кусочно-линейная функция

```c
input x;
output y;
const x1 = 0, x2 = 5, x3 = 10;
const y1 = 0, y2 = 3, y3 = 3, y4 = 0;

if (x <= x1) {
    y = y1;
} else if (x <= x2) {
    y = y1 + (y2 - y1) * (x - x1) / (x2 - x1);
} else if (x <= x3) {
    y = y2 + (y3 - y2) * (x - x2) / (x3 - x2);
} else {
    y = y4;
}
```

## 9. ШИМ-модулятор

```c
input duty_cycle;    // 0..1
output pwm;
const period = 0.001; // период ШИМ
var cycle_time;

cycle_time = mod(t, period);
pwm = (cycle_time < duty_cycle * period) ? 1 : 0;
```

## 10. Квадратурный генератор (sin + cos)

```c
output sine, cosine;
const omega = 2 * 3.14159 * 1.0; // 1 Гц
init phase = 0;

phase = phase + omega * h;
if (phase > 2 * 3.14159) { phase = phase - 2 * 3.14159; }
sine = sin(phase);
cosine = cos(phase);
```

## Бонус: Гирлянда на выходные

```c
output y;
const N = 8;
var i;

y = 0;
for (i = 0; i < N; i++) {
    y = y + sin((i + 1) * t) / (i + 1);
}
```
