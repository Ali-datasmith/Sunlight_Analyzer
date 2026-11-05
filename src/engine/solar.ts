/**
 * Solar position engine in TypeScript for Sunlight & Shadow Analyzer.
 * Implements NOAA General Solar Position Calculations (Meeus 1998)
 * with atmospheric refraction correction.
 */

import { Vec3, EL_MIN_DEG } from './geometry';

export interface SunState {
  azimuthDeg: number;
  elevationDeg: number;
  isDaytime: boolean;
  shadowsActive: boolean;
  declinationDeg: number;
  eotMin: number;
  hourAngleDeg: number;
}

export function solarPosition(
  latDeg: number,
  lonDeg: number,
  year: number,
  month: number,
  day: number,
  localMinute: number,
  tzOffsetHours: number
): SunState {
  // Julian Day
  const a = Math.floor((14 - month) / 12);
  const y = year + 4800 - a;
  const m = month + 12 * a - 3;
  const jdn =
    day +
    Math.floor((153 * m + 2) / 5) +
    365 * y +
    Math.floor(y / 4) -
    Math.floor(y / 100) +
    Math.floor(y / 400) -
    32045;

  const jd = jdn - 0.5 + localMinute / 1440.0 - tzOffsetHours / 24.0;
  const jc = (jd - 2451545.0) / 36525.0;

  // Geometric Mean Longitude
  const l0 = (280.46646 + jc * (36000.76983 + 0.0003032 * jc)) % 360.0;

  // Mean Anomaly
  const mDeg = 357.52911 + jc * (35999.05029 - 0.0001537 * jc);
  const mRad = (mDeg * Math.PI) / 180.0;

  // Eccentricity
  const e = 0.016708634 - jc * (0.000042037 + 0.0000001267 * jc);

  // Equation of center
  const c =
    Math.sin(mRad) * (1.914602 - jc * (0.004817 + 0.000014 * jc)) +
    Math.sin(2.0 * mRad) * (0.019993 - 0.000101 * jc) +
    Math.sin(3.0 * mRad) * 0.000289;

  // Apparent Longitude
  const omega = 125.04 - 1934.136 * jc;
  const omegaRad = (omega * Math.PI) / 180.0;
  const lambdaApp = l0 + c - 0.00569 - 0.00478 * Math.sin(omegaRad);

  // Obliquity
  const eps0 =
    23.0 + (26.0 + (21.448 - jc * (46.815 + jc * (0.00059 - 0.001813 * jc))) / 60.0) / 60.0;
  const eps = eps0 + 0.00256 * Math.cos(omegaRad);
  const epsRad = (eps * Math.PI) / 180.0;
  const lambdaRad = (lambdaApp * Math.PI) / 180.0;

  // Declination
  const sinDelta = Math.sin(epsRad) * Math.sin(lambdaRad);
  const deltaDeg = (Math.asin(Math.max(-1.0, Math.min(1.0, sinDelta))) * 180.0) / Math.PI;
  const deltaRad = (deltaDeg * Math.PI) / 180.0;

  // Equation of Time
  const yVal = Math.tan(epsRad / 2.0) ** 2;
  const l0Rad = (l0 * Math.PI) / 180.0;
  const eotRad =
    yVal * Math.sin(2.0 * l0Rad) -
    2.0 * e * Math.sin(mRad) +
    4.0 * e * yVal * Math.sin(mRad) * Math.cos(2.0 * l0Rad) -
    0.5 * yVal * yVal * Math.sin(4.0 * l0Rad) -
    1.25 * e * e * Math.sin(2.0 * mRad);
  const eotMin = 4.0 * ((eotRad * 180.0) / Math.PI);

  // Solar Time & Hour Angle
  const tst = (localMinute + eotMin + 4.0 * lonDeg - 60.0 * tzOffsetHours) % 1440.0;
  const hourAngleDeg = tst / 4.0 - 180.0;
  const hourAngleRad = (hourAngleDeg * Math.PI) / 180.0;

  // Zenith & Geometric Elevation
  const phiRad = (latDeg * Math.PI) / 180.0;
  const cosThetaZ =
    Math.sin(phiRad) * Math.sin(deltaRad) +
    Math.cos(phiRad) * Math.cos(deltaRad) * Math.cos(hourAngleRad);
  const thetaZDeg =
    (Math.acos(Math.max(-1.0, Math.min(1.0, cosThetaZ))) * 180.0) / Math.PI;
  const elGeometric = 90.0 - thetaZDeg;

  // Azimuth
  const sinThetaZ = Math.sin((thetaZDeg * Math.PI) / 180.0);
  let azimuthDeg = 180.0;
  if (Math.abs(sinThetaZ) >= 1e-9) {
    const cosPsi =
      (Math.sin(phiRad) * cosThetaZ - Math.sin(deltaRad)) / (Math.cos(phiRad) * sinThetaZ);
    const psiDeg =
      (Math.acos(Math.max(-1.0, Math.min(1.0, cosPsi))) * 180.0) / Math.PI;
    if (hourAngleDeg > 0) {
      azimuthDeg = (psiDeg + 180.0) % 360.0;
    } else {
      azimuthDeg = (540.0 - psiDeg) % 360.0;
    }
  }

  // Atmospheric Refraction (arcsec)
  const h = elGeometric;
  let refractionArcsec = 0.0;
  if (h > 85.0) {
    refractionArcsec = 0.0;
  } else if (5.0 < h && h <= 85.0) {
    const tanH = Math.tan((h * Math.PI) / 180.0);
    refractionArcsec = 58.1 / tanH - 0.07 / (tanH ** 3) + 0.000086 / (tanH ** 5);
  } else if (-0.575 < h && h <= 5.0) {
    refractionArcsec = 1735.0 + h * (-518.2 + h * (103.4 + h * (-12.79 + 0.711 * h)));
  } else {
    const tanH = Math.tan((h * Math.PI) / 180.0);
    refractionArcsec = Math.abs(tanH) > 1e-6 ? -20.772 / tanH : 0.0;
  }

  const elApparent = elGeometric + refractionArcsec / 3600.0;

  return {
    azimuthDeg,
    elevationDeg: elApparent,
    isDaytime: elApparent > 0.0,
    shadowsActive: elApparent >= EL_MIN_DEG,
    declinationDeg: deltaDeg,
    eotMin,
    hourAngleDeg,
  };
}

export function sunVector(azimuthDeg: number, elevationDeg: number): Vec3 {
  const radAz = (azimuthDeg * Math.PI) / 180.0;
  const radEl = (elevationDeg * Math.PI) / 180.0;
  const cosEl = Math.cos(radEl);
  return new Vec3(
    cosEl * Math.sin(radAz),
    cosEl * Math.cos(radAz),
    Math.sin(radEl)
  );
}

export function sunriseSunset(
  latDeg: number,
  lonDeg: number,
  year: number,
  month: number,
  day: number,
  tzOffsetHours: number
): [number | null, number | null] {
  let firstMin: number | null = null;
  let lastMin: number | null = null;

  for (let m = 0; m < 1440; m++) {
    const sun = solarPosition(latDeg, lonDeg, year, month, day, m, tzOffsetHours);
    if (sun.isDaytime) {
      if (firstMin === null) firstMin = m;
      lastMin = m;
    }
  }

  if (firstMin === null) return [null, null];
  if (firstMin === 0 && lastMin === 1439) return [0, 1439];
  return [firstMin, lastMin];
}
