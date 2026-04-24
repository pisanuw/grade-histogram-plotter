import logging
import os
import statistics
from datetime import datetime

from flask import Flask, render_template, request
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_wtf.csrf import CSRFProtect

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'dev-only-change-in-prod')
logging.basicConfig(level=logging.INFO)

csrf = CSRFProtect(app)
limiter = Limiter(get_remote_address, app=app, storage_uri="memory://")

DEFAULT_CUTOFFS = [50.0, 60.0, 70.0, 80.0, 90.0]
DEFAULT_GRADES = "70\n75\n80\n85\n85\n85\n75\n80\n85\n85\n85\n75\n80\n85\n85\n85\n90\n100"
MAX_GRADES = 1000


@app.after_request
def set_security_headers(response):
    response.headers['Content-Security-Policy'] = (
        "default-src 'self'; "
        "script-src 'self' https://cdn.jsdelivr.net 'unsafe-inline'; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data:;"
    )
    return response


def parse_grade_text(text):
    normalized = text.replace(',', '\n').replace('\t', '\n')
    return [x.strip() for x in normalized.split('\n') if x.strip()]


def get_grades_and_text():
    file = request.files.get('grades_file')
    if file and file.filename:
        content = file.read().decode('utf-8', errors='ignore')
        grades = parse_grade_text(content)
        return grades, '\n'.join(grades)
    raw = request.form.get('grades', '')
    return parse_grade_text(raw), raw.strip()


def get_cutoffs():
    return parse_cutoffs(request.form.get('cutoffs', ''))


def format_cutoff(value):
    value = float(value)
    return str(int(value)) if value.is_integer() else str(value)


def parse_cutoffs(raw_cutoffs):
    buckets = [x.strip() for x in raw_cutoffs.split('\n') if x.strip()]
    if not buckets:
        return DEFAULT_CUTOFFS.copy()

    try:
        parsed = [float(x) for x in buckets]
    except ValueError as exc:
        raise ValueError('Cutoffs must contain only numbers, one per line.') from exc

    if parsed != sorted(parsed):
        raise ValueError('Cutoffs must be in ascending order.')

    if len(set(parsed)) != len(parsed):
        raise ValueError('Cutoffs must not contain duplicates.')

    return parsed


def buckets2labels(cutoffs):
    labels = [f"<{format_cutoff(cutoffs[0])}"]
    for i in range(1, len(cutoffs)):
        lower = format_cutoff(cutoffs[i - 1])
        upper_value = cutoffs[i] - 1 if float(cutoffs[i]).is_integer() else cutoffs[i]
        upper = format_cutoff(upper_value)
        labels.append(f"{lower}-{upper}")
    labels.append(f">={format_cutoff(cutoffs[-1])}")
    labels.append("NaN")
    return labels


def process_post():
    ip_addr = request.environ.get('REMOTE_ADDR', 'unknown')
    timestamp = datetime.now().isoformat(timespec='seconds')

    cutoffs_text = request.form.get('cutoffs', '').strip()
    grades, grades_text = get_grades_and_text()

    try:
        cutoffs = get_cutoffs()
        chart_data, stats, nan_count = compute_chart_data(grades, cutoffs)
    except ValueError as exc:
        logging.info("%s: %s error=%s", timestamp, ip_addr, exc)
        return render_template(
            'input-grades.html',
            default_cutoffs=cutoffs_text or "\n".join(format_cutoff(x) for x in DEFAULT_CUTOFFS),
            default_grades=grades_text or DEFAULT_GRADES,
            error_message=str(exc),
        ), 400

    logging.info("%s: %s grades=%d cutoffs=%s", timestamp, ip_addr, len(grades),
                 cutoffs_text or 'default')
    return render_template(
        'result.html',
        chart_data=chart_data,
        stats=stats,
        nan_count=nan_count,
        cutoffs_text=cutoffs_text,
        grades_text=grades_text,
    )


@app.route("/", methods=['POST', 'GET'])
@limiter.limit("20 per minute", exempt_when=lambda: request.method == "GET")
def hello_world():
    if request.method == 'GET':
        return render_template(
            'input-grades.html',
            default_cutoffs="\n".join(format_cutoff(x) for x in DEFAULT_CUTOFFS),
            default_grades=DEFAULT_GRADES,
            error_message=None,
        )
    return process_post()


@app.route("/health")
@limiter.exempt
def health():
    return "OK", 200


def compute_chart_data(data, cutoffs):
    if not data:
        raise ValueError('Enter at least one grade.')
    if len(data) > MAX_GRADES:
        raise ValueError(f'Too many grades. Maximum is {MAX_GRADES}.')

    numeric = [float(x) for x in data if is_float(x)]
    nan_count = len(data) - len(numeric)

    xs = buckets2labels(cutoffs)
    ys = data_into_buckets(data, cutoffs)
    if len(xs) > len(ys):
        xs.pop()

    total = sum(ys)
    stats = {
        'total': len(data),
        'mean': round(statistics.mean(numeric), 1) if numeric else 'n/a',
        'median': round(statistics.median(numeric), 1) if numeric else 'n/a',
        'stdev': str(round(statistics.stdev(numeric), 1)) if len(numeric) > 1 else 'n/a',
        'min': round(min(numeric), 1) if numeric else 'n/a',
        'max': round(max(numeric), 1) if numeric else 'n/a',
        'distribution': ys,
        'percentages': [int(round(x / total * 100)) for x in ys] if total else [],
    }
    chart_data = {'labels': xs, 'values': ys}
    return chart_data, stats, nan_count


def data_into_buckets(data, cutoffs):
    buckets = [0] * (len(cutoffs) + 2)
    for grade in data:
        if not is_float(grade):
            buckets[-1] += 1
            continue
        g = float(grade)
        for i, cutoff in enumerate(cutoffs):
            if g < cutoff:
                buckets[i] += 1
                break
        else:
            buckets[-2] += 1
    if buckets[-1] == 0:
        buckets.pop()
    return buckets


def is_float(s):
    try:
        float(s)
        return True
    except ValueError:
        return False


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
