"""SLR identifies command mapping. It does not measure payload leveling."""
import numpy as np
from sklearn.linear_model import LinearRegression
from sklearn.metrics import mean_absolute_error, r2_score


def fit_slr(df, axis='Roll', minimum=60):
    xname, yname = ('roll', 'top') if axis == 'Roll' else ('pitch', 'bottom')
    # Never train across a device reset/out-of-order timestamp; deduplicate snapshots.
    stamps = df.t_ms.to_numpy()
    resets = np.where(np.diff(stamps) < 0)[0]
    if len(resets):
        df = df.iloc[resets[-1]+1:]
    healthy = df[df.sensor_ok.astype(bool)].drop_duplicates('t_ms',keep='last').copy()
    if len(healthy) < minimum:
        raise ValueError(f'Need {minimum} healthy samples from one continuous device run; have {len(healthy)}.')
    split = int(len(healthy)*.7)
    train, test = healthy.iloc[:split], healthy.iloc[split:]
    if np.ptp(train[xname]) < 5:
        raise ValueError('Training needs at least 5° of tilt variation. Gently tilt the base in both directions.')
    model = LinearRegression().fit(train[[xname]], train[yname])
    pred = model.predict(test[[xname]])
    baseline = np.full(len(test), train[yname].mean())
    return dict(model=model, train=train, test=test, predicted=pred,
        mae=mean_absolute_error(test[yname], pred),
        baseline_mae=mean_absolute_error(test[yname], baseline),
        r2=r2_score(test[yname], pred) if np.ptp(test[yname]) > 1e-6 else None,
        slope=float(model.coef_[0]), intercept=float(model.intercept_), x=xname, y=yname)


def fault_events(df, tilt_limit=35, servo_min=0, servo_max=180):
    if df.empty:
        return df
    flags = {
        'Sensor read failed': ~df.sensor_ok.astype(bool),
        'Base tilt above advisory threshold': df[['roll', 'pitch']].abs().max(axis=1) > tilt_limit,
        'Servo command at configured limit': ((df[['top', 'bottom']] <= servo_min+1) |
                                                (df[['top', 'bottom']] >= servo_max-1)).any(axis=1),
    }
    events = []
    for name, mask in flags.items():
        starts = mask & ~mask.shift(1, fill_value=False)
        for index in df.index[starts]:
            events.append({'time_s': round(df.loc[index, 't_ms']/1000, 2), 'event': name})
    import pandas as pd
    return pd.DataFrame(events, columns=['time_s', 'event']).sort_values('time_s')
