# SimInTech Code Library

Первая в мире открытая библиотека кода, примеров и шаблонов для **SimInTech** — российской среды моделирования динамических систем.

## Почему этот проект существует

SimInTech — мощный инструмент для инженеров и студентов. Но экосистема пуста: нет форумов, нет StackOverflow, нет AI-помощников. Эта библиотека — первый шаг к заполнению вакуума.

## Содержание

| Раздел | Описание |
|--------|----------|
| `blocks/` | Примеры для каждого типа блоков |
| `patterns/` | Типовые схемы: ПИД, пространство состояний, обратная связь |
| `language/` | Полный справочник внутреннего языка программирования |
| `tutorials/` | Пошаговые руководства для начинающих |

## Быстрый старт

```c
// Простейшая программа SimInTech
input u;
output y;
y = u * 2.5;
```

```c
// ПИД-регулятор
const Kp = 1.5, Ki = 0.8, Kd = 0.3;
var error, integral, derivative;
var prev_error = 0;
init integral = 0;
input setpoint, measurement;
output control;

error = setpoint - measurement;
integral = integral + error * h;
derivative = (error - prev_error) / h;
control = Kp * error + Ki * integral + Kd * derivative;
prev_error = error;
```

## Связанные проекты

- [SimInTech AI Helper](https://github.com/savant/simintech-ai-helper) — AI-ассистент (OpenClaw AgentSkill)
- @SimInTechHelper — Telegram-бот-помощник

## Лицензия

MIT
