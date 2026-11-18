"""Cell styles as Google `CellFormat`s: colours, text, wrapping, borders, conditional rules."""
import re

from ._common import SheetsClientError, _choice


_NUMBER_FORMAT_TYPES = ('NUMBER', 'CURRENCY', 'PERCENT', 'DATE', 'TIME',
                        'DATE_TIME', 'SCIENTIFIC', 'TEXT')

_ALIGN = {'left': 'LEFT', 'center': 'CENTER', 'right': 'RIGHT'}

_VALIGN = {'top': 'TOP', 'middle': 'MIDDLE', 'bottom': 'BOTTOM'}

_BORDER_KEYS = ('borders', 'border_color')

_STYLE_KEYS = ('background', 'color', 'bold', 'italic', 'font_size', 'wrap', 'align',
               'valign') + _BORDER_KEYS

_HEX = re.compile(r'#?([0-9a-fA-F]{6})')

_BORDER_SIDES = {'all': ('top', 'bottom', 'left', 'right', 'innerHorizontal', 'innerVertical'),
                 'outer': ('top', 'bottom', 'left', 'right'),
                 'none': ('top', 'bottom', 'left', 'right', 'innerHorizontal', 'innerVertical')}

#: `when` of a conditional format → (Google condition type, number of values it takes).
_CONDITIONS = {
    'number_greater': ('NUMBER_GREATER', 1), 'number_greater_or_equal': ('NUMBER_GREATER_THAN_EQ', 1),
    'number_less': ('NUMBER_LESS', 1), 'number_less_or_equal': ('NUMBER_LESS_THAN_EQ', 1),
    'number_eq': ('NUMBER_EQ', 1), 'number_between': ('NUMBER_BETWEEN', 2),
    'text_contains': ('TEXT_CONTAINS', 1), 'text_eq': ('TEXT_EQ', 1),
    'blank': ('BLANK', 0), 'not_blank': ('NOT_BLANK', 0), 'formula': ('CUSTOM_FORMULA', 1),
}

#: What a conditional format may set: Google refuses size, alignment and wrapping there.
_CONDITIONAL_STYLE_KEYS = ('background', 'color', 'bold', 'italic')


def _rgb(value, key: str) -> dict:
    """`#d9d9d9` → the API's 0..1 channels."""
    m = _HEX.fullmatch(str(value).strip())
    if not m:
        raise SheetsClientError(f"style.{key}: a colour as #rrggbb (got {value!r})")
    h = m.group(1)
    return {c: int(h[i:i + 2], 16) / 255 for c, i in (('red', 0), ('green', 2), ('blue', 4))}


def _flag(value, key: str) -> bool:
    if not isinstance(value, bool):
        raise SheetsClientError(f"style.{key}: true or false (got {value!r})")
    return value


def _cell_format(style: dict) -> tuple:
    """A `style` dict as a `CellFormat` and the field mask of exactly what it sets.

    An unknown key is refused, naming the valid ones: a silently ignored key would
    leave the agent believing the sheet is formatted."""
    if not isinstance(style, dict) or not style:
        raise SheetsClientError(f"style: an object with at least one of {', '.join(_STYLE_KEYS)}")
    unknown = sorted(set(style) - set(_STYLE_KEYS))
    if unknown:
        raise SheetsClientError(
            f"style: unknown key(s) {', '.join(unknown)}; valid: {', '.join(_STYLE_KEYS)}")
    fmt: dict = {}
    fields: list = []
    text: dict = {}
    if 'background' in style:
        fmt['backgroundColor'] = _rgb(style['background'], 'background')
        fields.append('backgroundColor')
    if 'color' in style:
        text['foregroundColor'] = _rgb(style['color'], 'color')
    for key in ('bold', 'italic'):
        if key in style:
            text[key] = _flag(style[key], key)
    if 'font_size' in style:
        size = style['font_size']
        if isinstance(size, bool) or not isinstance(size, int) or not 1 <= size <= 400:
            raise SheetsClientError(f"style.font_size: points, 1 to 400 (got {size!r})")
        text['fontSize'] = size
    if text:
        fmt['textFormat'] = text
        fields += [f'textFormat.{k}' for k in text]
    if 'wrap' in style:
        fmt['wrapStrategy'] = 'WRAP' if _flag(style['wrap'], 'wrap') else 'OVERFLOW_CELL'
        fields.append('wrapStrategy')
    if 'align' in style:
        fmt['horizontalAlignment'] = _choice(_ALIGN, style['align'], 'align')
        fields.append('horizontalAlignment')
    if 'valign' in style:
        fmt['verticalAlignment'] = _choice(_VALIGN, style['valign'], 'valign')
        fields.append('verticalAlignment')
    return fmt, fields


def _borders(style: dict) -> dict:
    """`borders` (+ `border_color`) as the sides of an `updateBorders` request."""
    if 'borders' not in style:
        raise SheetsClientError("style.border_color: goes with style.borders (all | outer | none)")
    kind = str(style['borders']).strip().lower()
    if kind not in _BORDER_SIDES:
        raise SheetsClientError(f"style.borders: one of all | outer | none (got {style['borders']!r})")
    if kind == 'none':
        line = {'style': 'NONE'}
    else:
        line = {'style': 'SOLID', 'color': _rgb(style.get('border_color', '#000000'), 'border_color')}
    return {side: line for side in _BORDER_SIDES[kind]}


def _conditional_rule(rule: dict) -> dict:
    """A `rule` dict as a Google `ConditionalFormatRule` (without its ranges)."""
    if not isinstance(rule, dict) or set(rule) - {'when', 'values', 'style'} or 'when' not in rule:
        raise SheetsClientError(
            'rule: {"when": …, "values": […], "style": {…}} — e.g. {"when": "number_less", '
            '"values": [0], "style": {"background": "#f4cccc"}}')
    when = rule['when']
    if when not in _CONDITIONS:
        raise SheetsClientError(f"rule.when: one of {' | '.join(_CONDITIONS)} (got {when!r})")
    kind, arity = _CONDITIONS[when]
    values = rule.get('values', [])
    if not isinstance(values, list) or len(values) != arity:
        raise SheetsClientError(f"rule.values: {arity} value(s) for {when!r} (got {values!r})")
    style = rule.get('style')
    if not isinstance(style, dict) or not style:
        raise SheetsClientError(
            f"rule.style: an object with at least one of {', '.join(_CONDITIONAL_STYLE_KEYS)}")
    extra = sorted(set(style) - set(_CONDITIONAL_STYLE_KEYS))
    if extra:
        raise SheetsClientError(
            f"rule.style: {', '.join(extra)} not allowed in a conditional format; "
            f"valid: {', '.join(_CONDITIONAL_STYLE_KEYS)}")
    fmt, _ = _cell_format(style)
    condition: dict = {'type': kind}
    if values:
        condition['values'] = [{'userEnteredValue': str(v)} for v in values]
    return {'booleanRule': {'condition': condition, 'format': fmt}}
