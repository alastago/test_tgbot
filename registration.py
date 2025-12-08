import aiohttp
import asyncio
from datetime import datetime
from config import LOGFILE

def log(text: str):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(LOGFILE, "a", encoding="utf-8") as f:
        f.write(f"[{ts}] {text}\n")


async def register_team_on_quizplease(
    game_id: int,
    team_name: str,
    captain_name: str,
    email: str,
    phone: str,
    players_count: int = 5,
    comment: str = "Автозапись"
):
    url = f"https://quizplease.ru/game-page?id={game_id}"

    data = {
        "record-from-form": "1",
        "QpRecord[teamName]": team_name,
        "QpRecord[captainName]": captain_name,
        "QpRecord[email]": email,
        "QpRecord[phone]": phone,
        "QpRecord[count]": str(players_count),
        "QpRecord[comment]": comment,
        "QpRecord[custom_fields_values]": "[]",
        "QpRecord[first_time]": "0",
        "certificates[]": "",
        "QpRecord[is_agreed_to_mailing]": "1",
        "QpRecord[game_id]": str(game_id),
        "QpRecord[max_people_active]": "",
        "reservation": "",
        "QpRecord[site_content_id]": "",
    }

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36",
        "Origin": "https://quizplease.ru",
        "Referer": url,
        "Content-Type": "application/x-www-form-urlencoded",
    }

    async with aiohttp.ClientSession() as session:
        try:
            async with session.post(url, data=data, headers=headers, allow_redirects=False) as resp:
                log(f"POST {url} -> status {resp.status}")
                location = resp.headers.get("Location", "")
                
                # Проверяем success
                if "success=" in location:
                    code = location.split("success=")[1]
                    code_map = {
                        "1": "Спасибо, что записались! (Успех)",
                        "2": "Упс! Что-то пошло не так. (Запись не выполнена)",
                        "3": "Команда с таким названием уже зарегистрирована на один из дней пакета. (Запись не выполнена)",
                        "4": "Вы поставлены в очередь на регистрацию. (Запись выполнена, вид записи неизвестен)",
                        "5": "Отлично! Вы записаны в резерв. (Запись выполнена в резерв)",
                        "6": "Упс, места на игру уже закончились. (Запись не выполнена)"
                    }
                    message = code_map.get(code, f"Неизвестный код success={code}")
                    log(f"Результат регистрации: {message}")
                    return code, message
                else:
                    text = await resp.text()
                    log(f"Регистрация не прошла, нет success в Location. Ответ сервера: {text[:200]}...")
                    return None, "Нет success в Location"

        except Exception as e:
            log(f"Ошибка при регистрации команды: {e}")
            return None, str(e)
