"use client";

import { useState, useEffect, useCallback } from "react";

export interface GeoLocation {
  latitude: number;
  longitude: number;
  displayName?: string;
}

export type GeoStatus = "idle" | "requesting" | "geocoding" | "resolved" | "denied" | "error";

export function useGeolocation() {
  const [location, setLocation] = useState<GeoLocation | null>(null);
  const [status, setStatus] = useState<GeoStatus>("idle");
  const [error, setError] = useState<string | null>(null);

  const reverseGeocode = useCallback(async (lat: number, lng: number): Promise<GeoLocation> => {
    const base: GeoLocation = { latitude: lat, longitude: lng };
    try {
      const res = await fetch(`/api/geo?lat=${lat}&lng=${lng}`);
      if (!res.ok) return base;
      const data = await res.json();
      return { ...base, ...data };
    } catch {
      return base;
    }
  }, []);

  const detect = useCallback(() => {
    if (!navigator.geolocation) {
      setStatus("error");
      setError("Geolocation is not supported by this browser");
      return;
    }

    setStatus("requesting");
    setError(null);

    navigator.geolocation.getCurrentPosition(
      async (position) => {
        const { latitude, longitude } = position.coords;
        setStatus("geocoding");
        const geo = await reverseGeocode(latitude, longitude);
        setLocation(geo);
        setStatus("resolved");
      },
      (err) => {
        if (err.code === err.PERMISSION_DENIED) {
          setStatus("denied");
          setError("Location access was denied");
        } else if (err.code === err.POSITION_UNAVAILABLE) {
          setStatus("error");
          setError("Location information is unavailable");
        } else if (err.code === err.TIMEOUT) {
          setStatus("error");
          setError("Location request timed out");
        } else {
          setStatus("error");
          setError("An unknown error occurred");
        }
      },
      { enableHighAccuracy: false, timeout: 10000, maximumAge: 300000 }
    );
  }, [reverseGeocode]);

  useEffect(() => {
    detect();
  }, [detect]);

  return { location, status, error, retry: detect };
}
