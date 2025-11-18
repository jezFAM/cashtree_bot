# CLAUDE.md - AI Assistant Guide for cashtree_bot

## Project Overview

**cashtree_bot** is a production-grade Telegram bot designed for automated Q&A collection and management from Korean review platforms. It serves the "Cashtree" service - a rewards platform where users answer questions about business reviews.

### Core Purpose
- Scrape review data from Naver Place, Naver Smart Store, and Kakao Place
- Collect and manage question-answer pairs
- Provide answers to users via Telegram interface with role-based access control
- Bypass bot detection using advanced stealth techniques

### Key Characteristics
- **Production System**: Active deployment with real users
- **Korean Market**: All user-facing text is in Korean (한글)
- **Async-First**: Heavily uses Python's asyncio framework
- **Anti-Detection**: Sophisticated bot bypass mechanisms with Playwright
- **Single Monolith**: 8,657 lines in one main file (cashtree_bot.py)

---

## Codebase Structure

### File Organization

```
/home/user/cashtree_bot/
├── cashtree_bot.py              # Main application (8,657 lines)
├── test_playwright.py           # Playwright stealth testing (235 lines)
├── cashtree_bot.ini            # Configuration file
├── cashtree_answers.json       # Answer database (JSON)
├── cashtree_answerKey.bin      # Answer key data (pickle)
├── cashtree_user_info.bin      # User information (pickle)
├── cashtree_bot_version_info.txt # Version tracking
├── cashtree_help*.md           # User documentation (4 files)
└── README.md                    # Minimal readme
```

### Main Application Architecture (`cashtree_bot.py`)

#### Global Objects (initialized in `__main__`)
```python
configInfo      # ConfigInfo - INI configuration loader
proxyInfo       # ProxyInfo - Proxy management (HTTP/SOCKS)
telegramInfo    # TelegramInfo - Telegram bot setup
answerKeyInfo   # ImportFileInfo - Answer key pickle manager
naverBufInfo    # ImportFileInfo - Naver buffer pickle manager
userInfo        # ImportFileInfo - User data pickle manager
dataInfo        # DataInfo - Central data store (40+ fields)
```

#### Key Classes & Locations

| Class | Line | Responsibility |
|-------|------|----------------|
| `ScriptInfo` | 131 | Script metadata (version, paths) |
| `ConfigInfo` | 142 | INI file configuration management |
| `TelegramInfo` | 178 | Telegram bot initialization |
| `ProxyInfo` | 215 | Proxy configuration (HTTP/SOCKS) |
| `ImportFileInfo` | 232 | Pickle file I/O operations |
| `DataInfo` | 265 | Central data store with locks |
| `CookieManager` | 1065 | Domain-based cookie management |
| `BrowserLikeClient` | 1149 | HTTP client with Playwright fallback |

#### Functional Areas

**Web Scraping Functions** (lines ~2000-5000)
- `get_place_review()` - Naver Place reviews
- `get_place_blog()` - Naver Place blogs
- `get_store_review()` - Naver Smart Store reviews
- `get_kakao_place_review()` - Kakao Place reviews
- `fetch_with_playwright()` - Stealth browser automation

**Answer Management** (lines ~5000-6500)
- `add_answerInfo()` - CRUD operations for answers
- `update_answerInfo()` - Periodic answer updates
- `find_Answer_From_CollectedData()` - Multi-mode search
- `get_Answer_For_Selected_Problem()` - Answer retrieval

**Telegram Handlers** (lines ~6500-8500)
- `handle_channel_message()` - Channel message processing
- `run_admin_command()` - Admin command dispatcher
- 20+ command handlers (`/help`, `/답`, `/업뎃`, etc.)

**Utilities** (scattered throughout)
- `convertToInitialLetters()` - Korean initial consonant extraction
- `find_pattern_in_list()` - Wildcard pattern matching
- `normalize_spaces()` - Text normalization

---

## Technology Stack

### Core Dependencies
```
python 3.x
telegram (python-telegram-bot)  # Telegram Bot API
playwright                       # Browser automation
playwright-stealth              # Bot detection bypass
httpx                           # Async HTTP client
httpx-socks                     # Proxy support
beautifulsoup4                  # HTML parsing
aiofiles                        # Async file I/O
aioconsole                      # Async console
nest-asyncio                    # Nested event loops
tqdm                           # Progress bars
python-dateutil                # Date parsing
```

### Architecture Patterns
- **Async/Await**: All I/O operations are async
- **Dataclasses**: Configuration and data objects
- **Global State**: Shared state with asyncio.Lock
- **Fallback Chain**: httpx → Playwright on failure

---

## Key Conventions & Patterns

### 1. Naming Conventions
- **Functions**: `camelCase` (e.g., `get_place_review()`, `addAnswerInfo()`)
- **Classes**: `PascalCase` (e.g., `BrowserLikeClient`, `CookieManager`)
- **Constants**: `UPPER_SNAKE_CASE` (e.g., `MAX_RETRIES`)
- **Global objects**: `camelCase` (e.g., `configInfo`, `dataInfo`)

### 2. Language Usage
- **Code comments**: Korean (한글)
- **User-facing messages**: Korean with emojis (🔄, ✅, ❌)
- **Variable names**: English
- **Log messages**: Korean

### 3. Async Patterns

**Always use async/await**:
```python
async def my_function():
    async with aiofiles.open(file_path, 'w') as f:
        await f.write(data)
```

**Thread-safe data access**:
```python
async with dataInfo.answer_lock:
    # Modify shared answer data
    dataInfo.answer_data[key] = value
```

**Concurrent operations**:
```python
results = await asyncio.gather(
    fetch_naver(),
    fetch_kakao(),
    return_exceptions=True
)
```

### 4. Error Handling Pattern

```python
try:
    # Attempt operation
    result = await some_async_operation()
except Exception as e:
    # Log error
    await write_log(f"❌ 에러: {str(e)}")
    # Optionally notify via Telegram
    await send_telegram_message(f"오류 발생: {e}")
    # Return gracefully or retry
```

### 5. Fallback Chain Pattern

The codebase uses a sophisticated fallback mechanism:
```python
# Try httpx first (fast, lightweight)
try:
    response = await client.get(url)
except Exception:
    # Fall back to Playwright (slower, but bypasses detection)
    html = await fetch_with_playwright(url)
```

### 6. Cookie Management

**Critical**: Cookies are shared between httpx and Playwright:
```python
# Extract from Playwright
cookies = await page.context.cookies()
cookie_manager.set_cookies_from_playwright(cookies, domain)

# Use in httpx
headers = cookie_manager.get_cookies_for_url(url)
```

### 7. Configuration Access

Always access configuration through global objects:
```python
# ❌ DON'T: Hardcode values
max_answers = 10

# ✅ DO: Use dataInfo
max_answers = dataInfo.max_answer_cnt
```

---

## Development Workflows

### Making Changes to the Bot

1. **Read Configuration First**
   ```python
   # Configuration in cashtree_bot.ini
   # Runtime state in dataInfo
   # Persistent data in pickle files
   ```

2. **Respect Thread Safety**
   - Always use locks when modifying shared state
   - dataInfo has dedicated locks: `answer_lock`, `user_lock`

3. **Maintain Korean Language**
   - User messages must be in Korean
   - Add emojis for visual feedback (🔄 processing, ✅ success, ❌ error)

4. **Test with Playwright First**
   - Use `test_playwright.py` to verify bot detection bypass
   - Test URL changes or new scraping targets

5. **Update Version Info**
   - Update `cashtree_bot_version_info.txt` for significant changes

### Adding New Scraping Targets

1. **Create async function** following naming convention
2. **Use BrowserLikeClient** for automatic fallback
3. **Extract data with BeautifulSoup**
4. **Handle cookies properly** via CookieManager
5. **Add error handling** with Korean messages

Example template:
```python
async def get_new_platform_review(url: str) -> dict:
    """새로운 플랫폼에서 리뷰를 가져옵니다."""
    try:
        client = BrowserLikeClient(proxy_url=proxyInfo.proxy_url_http)
        response = await client.get(url)
        soup = BeautifulSoup(response.text, 'html.parser')

        # Extract data
        data = extract_review_data(soup)

        await client.close()
        return data
    except Exception as e:
        await write_log(f"❌ 리뷰 가져오기 실패: {e}")
        return {}
```

### Adding Telegram Commands

1. **Define handler function**:
```python
async def handle_my_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id

    # Check permissions if needed
    if str(chat_id) not in dataInfo.premium_member:
        await context.bot.send_message(chat_id, "⚠️ 프리미엄 멤버 전용 기능입니다.")
        return

    # Process command
    result = await my_command_logic()

    # Send response
    await context.bot.send_message(chat_id, f"✅ {result}")
```

2. **Register in application**:
```python
application.add_handler(CommandHandler('mycommand', handle_my_command))
```

3. **Update help documentation** in appropriate `cashtree_help*.md` file

---

## Testing Approach

### Current Test Coverage

**File**: `test_playwright.py`
- **Purpose**: Test Playwright-based bot detection bypass
- **Target**: Naver Smart Store (smartstore.naver.com)
- **Verifies**: HTTP status, cookie extraction, HTML retrieval

### Testing Strategy

1. **Stealth Testing**
   ```bash
   python test_playwright.py
   ```
   Expected output:
   - HTTP status 200
   - Cookies extracted (NNB, NID_AUT, etc.)
   - HTML content retrieved

2. **Manual Testing via Telegram**
   - Send commands to bot
   - Verify responses in Korean
   - Check logs for errors

3. **Data Integrity Checks**
   - Verify pickle files load correctly
   - Check JSON answer database structure
   - Validate configuration parsing

### Before Committing Changes

✅ **Checklist**:
- [ ] Run `test_playwright.py` successfully
- [ ] Test command via Telegram (if applicable)
- [ ] Verify Korean text displays correctly
- [ ] Check logs for errors
- [ ] Ensure async functions use `await` properly
- [ ] Verify thread-safe access to shared data
- [ ] Update version info if needed

---

## Important Files & Their Purposes

### Configuration & Data Files

| File | Format | Purpose | Backup? |
|------|--------|---------|---------|
| `cashtree_bot.ini` | INI | Configuration (proxy, Telegram, timings) | Yes |
| `cashtree_answers.json` | JSON | Answer database (searchable) | Critical |
| `cashtree_answerKey.bin` | Pickle | Answer key mappings | Critical |
| `cashtree_user_info.bin` | Pickle | User data, permissions | Critical |
| `cashtree_bot_version_info.txt` | Text | Version tracking | No |

### Code Files

| File | Lines | Purpose |
|------|-------|---------|
| `cashtree_bot.py` | 8,657 | Main application |
| `test_playwright.py` | 235 | Playwright stealth tests |

### Documentation Files

| File | Audience | Content |
|------|----------|---------|
| `cashtree_help.md` | All users | Basic commands |
| `cashtree_help_admin.md` | Admins | Admin commands |
| `cashtree_help_answerManager.md` | Answer managers | Answer management |
| `cashtree_help_premium.md` | Premium users | Premium features |

---

## Common Tasks & How to Approach Them

### Task: Fix Bot Detection Issues

**Location**: `fetch_with_playwright()` in cashtree_bot.py (around line 1500)

**Steps**:
1. Review recent changes to target website
2. Update stealth techniques in `test_playwright.py`
3. Test with `python test_playwright.py`
4. Apply working solution to `fetch_with_playwright()`
5. Update cookies if needed (store_nnb, store_fwb, store_buc)

**Key Points**:
- Playwright cookies must be preserved (see `BrowserLikeClient`)
- User-agent should match Playwright browser
- Referer headers are critical for Naver

### Task: Add New Answer Sources

**Location**: Answer management functions (around line 5000)

**Steps**:
1. Create scraping function (follow `get_place_review()` pattern)
2. Parse data into standard format
3. Call `add_answerInfo()` to add to database
4. Update `update_answerInfo()` for periodic refresh
5. Test search functionality

**Key Points**:
- Use locks when modifying `dataInfo.answer_data`
- Maintain answer key uniqueness
- Handle duplicates with `find_duplicate_urls()`

### Task: Modify User Permissions

**Location**: `cashtree_bot.ini` [DATA] section

**Members Lists**:
```ini
admin_member = ['46835960']
premium_member = ['46835960', '61817669', '5319272939', '129067327', 'console']
answer_manage_member = ['46835960', 'console']
```

**Steps**:
1. Edit INI file
2. Restart bot (configuration reloads)
3. Test permissions with user

**Note**: 'console' is special user for command-line access

### Task: Update Scraping Intervals

**Location**: `cashtree_bot.ini` [DATA] section

**Key Settings**:
```ini
answer_refresh_interval = 14400      # 4 hours
answer_refresh_error_interval = 1800 # 30 minutes on error
naver_buf_refresh_interval = 21600   # 6 hours
```

**Impact**: Lower values = more frequent updates, higher detection risk

### Task: Debug Cookie Issues

**Critical Cookies** (Naver Smart Store):
- `store_nnb`: Naver login state
- `store_fwb`: Feature toggle
- `store_buc`: User bucket
- `store_token`: Authentication token

**Debugging**:
1. Check `CookieManager.get_cookies_for_url()` output
2. Verify cookies in `cashtree_bot.ini` [DATA] section
3. Extract fresh cookies using Playwright:
   ```python
   cookies = await page.context.cookies()
   ```
4. Update INI file with new cookie values

---

## Gotchas & Special Considerations

### 1. Korean Language Handling

❌ **DON'T**:
```python
await context.bot.send_message(chat_id, "Success!")
```

✅ **DO**:
```python
await context.bot.send_message(chat_id, "✅ 성공적으로 완료되었습니다!")
```

### 2. Async Context Managers

❌ **DON'T**:
```python
file = open('data.txt', 'w')
file.write(data)
file.close()
```

✅ **DO**:
```python
async with aiofiles.open('data.txt', 'w', encoding='utf-8') as f:
    await f.write(data)
```

### 3. Lock Usage

❌ **DON'T**:
```python
dataInfo.answer_data[key] = value  # Race condition!
```

✅ **DO**:
```python
async with dataInfo.answer_lock:
    dataInfo.answer_data[key] = value
```

### 4. Browser Context Cleanup

❌ **DON'T**:
```python
browser = await playwright.chromium.launch()
# ... use browser ...
# Forget to close!
```

✅ **DO**:
```python
async with async_playwright() as playwright:
    browser = await playwright.chromium.launch()
    # ... use browser ...
    # Automatically closes
```

### 5. Proxy Configuration

**HTTP vs SOCKS**:
- `proxy_url_http`: For httpx client (HTTP/HTTPS proxy)
- `proxy_url`: For Playwright (SOCKS proxy)

**Don't mix them up!**

### 6. Time-based Modes

The bot has scheduled modes (alert_mode, noti_mode, channel_noti_mode):
- Configured as time ranges in INI: `[['00:00', '02:00'], ['08:00', '23:59']]`
- Automatically toggle based on current time
- Affect notification behavior

### 7. Answer Search Modes

Different search prefixes trigger different behavior:
- No prefix: Normal keyword search
- `*` prefix: Wildcard pattern search (premium only)
- `@` prefix: Cross-reference search (premium only)
- Initial consonants (ㄱ, ㄴ, etc.): Korean initial search

### 8. Pickle File Corruption

**Symptom**: `pickle.UnpicklingError`

**Solution**:
```python
# Recreate from backup or initialize new
await answerKeyInfo.init_pickle(scriptInfo.script_path + configInfo.config['FILE']['answerKey'])
```

### 9. Telegram Rate Limits

**Limit**: 30 messages/second per chat

**Solution**: Use delays between bulk messages:
```python
for msg in messages:
    await context.bot.send_message(chat_id, msg)
    await asyncio.sleep(0.05)  # 50ms delay
```

### 10. Naver URL Changes

Naver frequently updates URLs and HTML structure:
- Monitor logs for parsing errors
- Check `get_place_review()` and similar functions
- Update CSS selectors or API endpoints

---

## Git Workflow

### Branch Strategy

**Current Branch**: `claude/claude-md-mi40grnt6ij1ckjs-01NcQsygNJ4paFQpptcRs1Rc`

**Branch Naming**:
- Feature branches: `claude/*-<session-id>`
- Must start with `claude/` and end with session ID
- Push will fail (403) if naming is incorrect

### Commit Guidelines

**Good Commit Messages**:
```
Fix Playwright browser crash errors (TargetClosedError)
Preserve and pass existing cookies to Playwright sessions
Refactor BrowserLikeClient to make store cookies optional
```

**Pattern**: `<Action> <what> [<context>]`

**Actions**: Fix, Add, Update, Refactor, Remove, Merge

### Push Workflow

```bash
# Develop on feature branch
git checkout -b claude/feature-name-<session-id>

# Make changes and commit
git add .
git commit -m "Add new feature description"

# Push with upstream tracking
git push -u origin claude/feature-name-<session-id>
```

**Note**: Retry on network errors (up to 4 times with exponential backoff)

### Pull Request Process

1. **Ensure all tests pass**
   ```bash
   python test_playwright.py
   ```

2. **Create PR** targeting main branch

3. **PR Description should include**:
   - What changed
   - Why it changed
   - Testing performed
   - Any configuration updates needed

---

## Recent Development Context

### Recent Commits (Last 5)

1. `c601a1a` - Merge PR #8: Fix Playwright browser errors
2. `e61a7eb` - Preserve and pass existing cookies to Playwright sessions
3. `16c1425` - Fix Playwright browser crash errors (TargetClosedError)
4. `4dfa6b8` - Merge PR #6: Review browser client storage
5. `d1aa789` - Refactor BrowserLikeClient to make store cookies optional

### Active Focus Areas

1. **Playwright Stability**
   - Recent fixes for TargetClosedError
   - Cookie preservation between sessions
   - Browser context management

2. **Cookie Management**
   - Making Naver Store cookies optional
   - Better cookie sharing between httpx/Playwright
   - Domain-based cookie storage

3. **Browser Detection Bypass**
   - Ongoing cat-and-mouse game with Naver
   - Stealth improvements in test_playwright.py

---

## Performance Considerations

### Resource Usage

**Heavy Operations**:
- Playwright browser launch (~2-3 seconds)
- Large JSON answer database loading
- Concurrent scraping (multiple sites)

**Optimization Tips**:
1. Reuse Playwright browser contexts when possible
2. Use httpx first, Playwright as fallback
3. Limit concurrent scraping operations
4. Cache answer data in memory (dataInfo)

### Rate Limiting

**External Services**:
- Naver: Aggressive bot detection, use delays
- Kakao: More lenient, still use reasonable delays
- Telegram: 30 msg/sec limit per chat

**Recommended Delays**:
```python
await asyncio.sleep(0.5)  # Between Naver requests
await asyncio.sleep(0.1)  # Between Kakao requests
await asyncio.sleep(0.05) # Between Telegram messages
```

---

## Debugging Tips

### Enable Verbose Logging

**Location**: `write_log()` function calls throughout code

**Add debugging**:
```python
await write_log(f"🔍 디버그: {variable_name} = {value}")
```

### Telegram Bot Not Responding

**Check**:
1. Token in `cashtree_bot.ini` is valid
2. Bot is running (check logs)
3. Chat ID is in allowed members list
4. Network/proxy connectivity

### Scraping Returns Empty Data

**Check**:
1. URL is still valid
2. HTML structure hasn't changed
3. Cookies are fresh (especially for Naver Store)
4. Bot detection triggered (check HTTP status)
5. Try Playwright directly (bypass httpx)

### Pickle Load Errors

**Symptoms**: `EOFError`, `UnpicklingError`

**Solutions**:
1. Check file permissions
2. Verify file isn't corrupted (check file size)
3. Reinitialize with `init_pickle()`
4. Restore from backup

### Korean Text Encoding Issues

**Always use UTF-8**:
```python
async with aiofiles.open(file_path, 'w', encoding='utf-8') as f:
    await f.write(korean_text)
```

---

## Quick Reference

### Essential Commands

```bash
# Run bot
python cashtree_bot.py

# Test Playwright stealth
python test_playwright.py

# Check configuration
cat cashtree_bot.ini

# View recent logs
tail -f cashtree_bot.log  # (if logging to file)
```

### Key File Paths

```python
scriptInfo.script_path              # /home/user/cashtree_bot/
configInfo.config_file              # cashtree_bot.ini
configInfo.config['FILE']['answerKey']    # cashtree_answerKey.bin
configInfo.config['FILE']['naverBuf']     # cashtree_naver_buf.bin
configInfo.config['FILE']['userInfo']     # cashtree_user_info.bin
```

### User Roles

| Role | Members | Capabilities |
|------|---------|--------------|
| Admin | `['46835960']` | All commands, config updates |
| Premium | `['46835960', '61817669', ...]` | Pattern search, @-search |
| Answer Manager | `['46835960', 'console']` | Answer CRUD operations |
| Regular | All others | Basic search only |

### Critical Global Objects

```python
configInfo    # Configuration from INI
proxyInfo     # Proxy settings
telegramInfo  # Telegram bot instance
dataInfo      # Central data store (USE LOCKS!)
answerKeyInfo # Answer key pickle
naverBufInfo  # Naver buffer pickle
userInfo      # User data pickle
```

---

## For Claude Code Assistants

### When Asked to Make Changes

1. **Always read the code first** using Read tool
2. **Check for Korean language** requirements
3. **Verify async/await** usage
4. **Look for lock usage** on shared data
5. **Test with** `test_playwright.py` if scraping-related
6. **Update version info** if significant change
7. **Use Korean** for user-facing messages

### When Debugging Issues

1. **Search for recent similar code** to follow patterns
2. **Check commit history** for context
3. **Look for Korean comments** explaining logic
4. **Test in isolation** before integrating
5. **Verify cookie handling** for Naver issues

### When Refactoring

⚠️ **WARNING**: This is a production system
- **Test thoroughly** before committing
- **Maintain backward compatibility** with data files
- **Preserve Korean language** in all messages
- **Keep async patterns** consistent
- **Don't break pickle file format**

### Common Requests

**"Fix Playwright errors"** → Check `fetch_with_playwright()` and `test_playwright.py`

**"Add new command"** → Follow Telegram handler pattern, register in main

**"Update scraping"** → Use BrowserLikeClient, handle cookies, add error handling

**"Change permissions"** → Edit `cashtree_bot.ini` [DATA] member lists

**"Debug search"** → Check `find_Answer_From_CollectedData()` and search modes

---

## Additional Resources

### External Documentation

- [python-telegram-bot](https://docs.python-telegram-bot.org/)
- [Playwright for Python](https://playwright.dev/python/)
- [httpx Documentation](https://www.python-httpx.org/)
- [BeautifulSoup4](https://www.crummy.com/software/BeautifulSoup/bs4/doc/)

### Internal Help Files

- `cashtree_help.md` - General user guide
- `cashtree_help_admin.md` - Admin commands
- `cashtree_help_answerManager.md` - Answer management
- `cashtree_help_premium.md` - Premium features

---

## Changelog

### Version History

See `cashtree_bot_version_info.txt` for detailed version history.

### This Document

**Created**: 2025-11-18
**Last Updated**: 2025-11-18
**Maintainer**: AI Assistant (Claude)

---

## Contact & Support

**Repository**: https://github.com/jezFAM/cashtree_bot

**For Issues**: Create GitHub issue or check recent commits for context

**Admin Chat ID**: 46835960 (see cashtree_bot.ini)

---

**END OF CLAUDE.MD**
