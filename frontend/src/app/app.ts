import { CommonModule } from '@angular/common';
import { HttpClient, HttpHeaders } from '@angular/common/http';
import { Component, inject, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { firstValueFrom } from 'rxjs';

type MenuOption = 'usuarios' | 'artistas';

interface LoginResponse {
  access_token: string;
}

interface Usuario {
  id: number;
  usuario: string;
  nombre: string;
  apellido: string;
}

interface Cancion {
  id?: number;
  titulo: string;
  album?: string | null;
  duracion_segundos?: number | null;
  anio_lanzamiento?: number | null;
}

interface Artista {
  id: number;
  nombre: string;
  apellido: string;
  nombre_artistico: string;
  genero: string;
  pais_origen: string;
  fecha_nacimiento?: string | null;
  biografia?: string | null;
  canciones: Cancion[];
}

interface ApiError {
  error?: {
    detail?: string;
  };
}

const AUTH_API = 'http://localhost:8001';
const ARTISTA_API = 'http://localhost:8002';

@Component({
  selector: 'app-root',
  imports: [CommonModule, ReactiveFormsModule],
  templateUrl: './app.html',
  styleUrl: './app.css',
})
export class App {
  private readonly fb = inject(FormBuilder);
  private readonly http = inject(HttpClient);

  protected readonly loginForm = this.fb.nonNullable.group({
    username: ['admin', Validators.required],
    password: ['123456', Validators.required],
  });

  protected readonly usuarioForm = this.fb.nonNullable.group({
    usuario: ['', Validators.required],
    nombre: ['', Validators.required],
    apellido: ['', Validators.required],
    password: ['', [Validators.required, Validators.minLength(4)]],
  });

  protected readonly passwordForm = this.fb.nonNullable.group({
    passwordActual: [''],
    passwordNueva: ['', [Validators.required, Validators.minLength(4)]],
  });

  protected readonly artistaForm = this.fb.nonNullable.group({
    nombre: ['', Validators.required],
    apellido: ['', Validators.required],
    nombre_artistico: ['', Validators.required],
    genero: ['', Validators.required],
    pais_origen: ['', Validators.required],
    fecha_nacimiento: [''],
    biografia: [''],
  });

  protected readonly cancionForm = this.fb.nonNullable.group({
    titulo: ['', Validators.required],
    album: [''],
    duracion_segundos: [''],
    anio_lanzamiento: [''],
  });

  protected readonly isLoggedIn = signal(false);
  protected readonly activeMenu = signal<MenuOption>('usuarios');
  protected readonly showUserModal = signal(false);
  protected readonly showPasswordModal = signal(false);
  protected readonly showArtistModal = signal(false);
  protected readonly loginLoading = signal(false);
  protected readonly usersLoading = signal(false);
  protected readonly artistsLoading = signal(false);
  protected readonly saveUserLoading = signal(false);
  protected readonly savePasswordLoading = signal(false);
  protected readonly saveArtistLoading = signal(false);
  protected readonly loginError = signal('');
  protected readonly userError = signal('');
  protected readonly artistError = signal('');
  protected readonly usuarios = signal<Usuario[]>([]);
  protected readonly artistas = signal<Artista[]>([]);
  protected readonly cancionesEnEdicion = signal<Cancion[]>([]);
  protected readonly editingUserId = signal<number | null>(null);
  protected readonly editingArtistaId = signal<number | null>(null);
  protected readonly passwordTargetUser = signal<Usuario | null>(null);

  private token = '';

  constructor() {
    this.restoreSession();
  }

  protected async iniciarSesion(): Promise<void> {
    if (this.loginForm.invalid) {
      this.loginForm.markAllAsTouched();
      return;
    }

    this.loginLoading.set(true);
    this.loginError.set('');

    try {
      const credentials = this.loginForm.getRawValue();
      const response = await firstValueFrom(
        this.http.post<LoginResponse>(`${AUTH_API}/login`, credentials),
      );

      this.token = response.access_token;
      localStorage.setItem('musica_token', this.token);
      this.isLoggedIn.set(true);
      await Promise.all([this.cargarUsuarios(), this.cargarArtistas()]);
    } catch (error) {
      this.loginError.set(this.readError(error, 'No se pudo iniciar sesion'));
    } finally {
      this.loginLoading.set(false);
    }
  }

  protected cerrarSesion(): void {
    this.isLoggedIn.set(false);
    this.token = '';
    this.usuarios.set([]);
    this.artistas.set([]);
    this.showUserModal.set(false);
    this.showPasswordModal.set(false);
    this.showArtistModal.set(false);
    this.editingUserId.set(null);
    this.editingArtistaId.set(null);
    this.passwordTargetUser.set(null);
    this.loginError.set('');
    this.userError.set('');
    this.artistError.set('');
    localStorage.removeItem('musica_token');
  }

  protected seleccionarMenu(menu: MenuOption): void {
    this.activeMenu.set(menu);
    if (menu === 'usuarios' && this.usuarios().length === 0) {
      void this.cargarUsuarios();
    }
    if (menu === 'artistas' && this.artistas().length === 0) {
      void this.cargarArtistas();
    }
  }

  protected abrirPopupUsuario(usuario?: Usuario): void {
    if (usuario) {
      this.editingUserId.set(usuario.id);
      this.usuarioForm.reset({
        usuario: usuario.usuario,
        nombre: usuario.nombre,
        apellido: usuario.apellido,
        password: '',
      });
      this.usuarioForm.controls.password.clearValidators();
      this.usuarioForm.controls.password.updateValueAndValidity();
    } else {
      this.editingUserId.set(null);
      this.usuarioForm.reset({
        usuario: '',
        nombre: '',
        apellido: '',
        password: '',
      });
      this.usuarioForm.controls.password.setValidators([Validators.required, Validators.minLength(4)]);
      this.usuarioForm.controls.password.updateValueAndValidity();
    }

    this.userError.set('');
    this.showPasswordModal.set(false);
    this.showArtistModal.set(false);
    this.showUserModal.set(true);
  }

  protected cerrarPopupUsuario(): void {
    this.showUserModal.set(false);
    this.editingUserId.set(null);
    this.userError.set('');
  }

  protected async guardarUsuario(): Promise<void> {
    if (this.usuarioForm.invalid) {
      this.usuarioForm.markAllAsTouched();
      return;
    }

    this.saveUserLoading.set(true);
    this.userError.set('');

    try {
      const formValue = this.usuarioForm.getRawValue();
      const editingId = this.editingUserId();

      if (editingId) {
        const body = {
          usuario: formValue.usuario,
          nombre: formValue.nombre,
          apellido: formValue.apellido,
        };
        await firstValueFrom(
          this.http.put<Usuario>(`${AUTH_API}/usuarios/${editingId}`, body, {
            headers: this.authHeaders(),
          }),
        );
      } else {
        await firstValueFrom(
          this.http.post<Usuario>(`${AUTH_API}/usuarios`, formValue, {
            headers: this.authHeaders(),
          }),
        );
      }

      this.showUserModal.set(false);
      this.editingUserId.set(null);
      await this.cargarUsuarios();
    } catch (error) {
      this.userError.set(this.readError(error, 'No se pudo guardar el usuario'));
    } finally {
      this.saveUserLoading.set(false);
    }
  }

  protected abrirPopupPassword(usuario: Usuario): void {
    this.passwordTargetUser.set(usuario);
    this.passwordForm.reset({
      passwordActual: '',
      passwordNueva: '',
    });
    this.userError.set('');
    this.showUserModal.set(false);
    this.showArtistModal.set(false);
    this.showPasswordModal.set(true);
  }

  protected cerrarPopupPassword(): void {
    this.showPasswordModal.set(false);
    this.passwordTargetUser.set(null);
    this.userError.set('');
  }

  protected async cambiarPasswordUsuario(): Promise<void> {
    const targetUser = this.passwordTargetUser();
    if (!targetUser) {
      return;
    }

    if (this.passwordForm.invalid) {
      this.passwordForm.markAllAsTouched();
      return;
    }

    this.savePasswordLoading.set(true);
    this.userError.set('');

    try {
      const formValue = this.passwordForm.getRawValue();
      const body: { password_nueva: string; password_actual?: string } = {
        password_nueva: formValue.passwordNueva,
      };
      if (formValue.passwordActual.trim().length > 0) {
        body.password_actual = formValue.passwordActual;
      }

      await firstValueFrom(
        this.http.put(`${AUTH_API}/usuarios/${targetUser.id}/password`, body, {
          headers: this.authHeaders(),
        }),
      );
      this.showPasswordModal.set(false);
      this.passwordTargetUser.set(null);
    } catch (error) {
      this.userError.set(this.readError(error, 'No se pudo cambiar la contrasena'));
    } finally {
      this.savePasswordLoading.set(false);
    }
  }

  protected async eliminarUsuario(usuario: Usuario): Promise<void> {
    const ok = window.confirm(`Quieres eliminar al usuario ${usuario.usuario}?`);
    if (!ok) {
      return;
    }

    try {
      await firstValueFrom(
        this.http.delete(`${AUTH_API}/usuarios/${usuario.id}`, {
          headers: this.authHeaders(),
        }),
      );
      await this.cargarUsuarios();
    } catch (error) {
      this.userError.set(this.readError(error, 'No se pudo eliminar el usuario'));
    }
  }

  protected async cargarUsuarios(): Promise<void> {
    if (!this.token) {
      return;
    }

    this.usersLoading.set(true);

    try {
      const data = await firstValueFrom(
        this.http.get<Usuario[]>(`${AUTH_API}/usuarios`, {
          headers: this.authHeaders(),
        }),
      );
      this.usuarios.set(data);
    } catch (error) {
      const message = this.readError(error, 'No se pudieron cargar usuarios');
      if (message.includes('Token invalido') || message.includes('Falta token')) {
        this.cerrarSesion();
      } else {
        this.userError.set(message);
      }
    } finally {
      this.usersLoading.set(false);
    }
  }

  protected abrirPopupArtista(artista?: Artista): void {
    if (artista) {
      this.editingArtistaId.set(artista.id);
      this.artistaForm.reset({
        nombre: artista.nombre,
        apellido: artista.apellido,
        nombre_artistico: artista.nombre_artistico,
        genero: artista.genero,
        pais_origen: artista.pais_origen,
        fecha_nacimiento: artista.fecha_nacimiento ?? '',
        biografia: artista.biografia ?? '',
      });
      this.cancionesEnEdicion.set(
        artista.canciones.map((cancion) => ({
          titulo: cancion.titulo,
          album: cancion.album ?? null,
          duracion_segundos: cancion.duracion_segundos ?? null,
          anio_lanzamiento: cancion.anio_lanzamiento ?? null,
        })),
      );
    } else {
      this.editingArtistaId.set(null);
      this.artistaForm.reset({
        nombre: '',
        apellido: '',
        nombre_artistico: '',
        genero: '',
        pais_origen: '',
        fecha_nacimiento: '',
        biografia: '',
      });
      this.cancionesEnEdicion.set([]);
    }

    this.cancionForm.reset({
      titulo: '',
      album: '',
      duracion_segundos: '',
      anio_lanzamiento: '',
    });

    this.artistError.set('');
    this.showUserModal.set(false);
    this.showPasswordModal.set(false);
    this.showArtistModal.set(true);
  }

  protected cerrarPopupArtista(): void {
    this.showArtistModal.set(false);
    this.editingArtistaId.set(null);
    this.cancionesEnEdicion.set([]);
    this.cancionForm.reset({
      titulo: '',
      album: '',
      duracion_segundos: '',
      anio_lanzamiento: '',
    });
    this.artistError.set('');
  }

  protected agregarCancionEnLista(): void {
    if (this.cancionForm.invalid) {
      this.cancionForm.markAllAsTouched();
      return;
    }

    const formValue = this.cancionForm.getRawValue();
    const titulo = this.safeText(formValue.titulo);
    if (!titulo) {
      return;
    }

    const nuevaCancion: Cancion = {
      titulo,
      album: this.safeText(formValue.album) || null,
      duracion_segundos: this.toNullableNumber(formValue.duracion_segundos, 1),
      anio_lanzamiento: this.toNullableNumber(formValue.anio_lanzamiento, 1900, 2200),
    };

    this.cancionesEnEdicion.set([...this.cancionesEnEdicion(), nuevaCancion]);
    this.cancionForm.reset({
      titulo: '',
      album: '',
      duracion_segundos: '',
      anio_lanzamiento: '',
    });
  }

  protected quitarCancionDeLista(index: number): void {
    const canciones = [...this.cancionesEnEdicion()];
    canciones.splice(index, 1);
    this.cancionesEnEdicion.set(canciones);
  }

  protected async guardarArtista(): Promise<void> {
    if (this.artistaForm.invalid) {
      this.artistaForm.markAllAsTouched();
      return;
    }

    this.saveArtistLoading.set(true);
    this.artistError.set('');

    try {
      const formValue = this.artistaForm.getRawValue();
      const body = {
        nombre: formValue.nombre,
        apellido: formValue.apellido,
        nombre_artistico: formValue.nombre_artistico,
        genero: formValue.genero,
        pais_origen: formValue.pais_origen,
        fecha_nacimiento: formValue.fecha_nacimiento || null,
        biografia: formValue.biografia || null,
        canciones: this.cancionesEnEdicion().map((cancion) => ({
          titulo: cancion.titulo,
          album: cancion.album ?? null,
          duracion_segundos: cancion.duracion_segundos ?? null,
          anio_lanzamiento: cancion.anio_lanzamiento ?? null,
        })),
      };

      const editingId = this.editingArtistaId();
      if (editingId) {
        await firstValueFrom(
          this.http.put<Artista>(`${ARTISTA_API}/artistas/${editingId}`, body, {
            headers: this.authHeaders(),
          }),
        );
      } else {
        await firstValueFrom(
          this.http.post<Artista>(`${ARTISTA_API}/artistas`, body, {
            headers: this.authHeaders(),
          }),
        );
      }

      this.showArtistModal.set(false);
      this.editingArtistaId.set(null);
      await this.cargarArtistas();
    } catch (error) {
      this.artistError.set(this.readError(error, 'No se pudo guardar el artista'));
    } finally {
      this.saveArtistLoading.set(false);
    }
  }

  protected async eliminarArtista(artista: Artista): Promise<void> {
    const ok = window.confirm(
      `Quieres eliminar al artista ${artista.nombre_artistico || `${artista.nombre} ${artista.apellido}`}?`,
    );
    if (!ok) {
      return;
    }

    try {
      await firstValueFrom(
        this.http.delete(`${ARTISTA_API}/artistas/${artista.id}`, {
          headers: this.authHeaders(),
        }),
      );
      await this.cargarArtistas();
    } catch (error) {
      this.artistError.set(this.readError(error, 'No se pudo eliminar el artista'));
    }
  }

  protected async cargarArtistas(): Promise<void> {
    if (!this.token) {
      return;
    }

    this.artistsLoading.set(true);

    try {
      const data = await firstValueFrom(
        this.http.get<Artista[]>(`${ARTISTA_API}/artistas`, {
          headers: this.authHeaders(),
        }),
      );
      this.artistas.set(data);
    } catch (error) {
      const message = this.readError(error, 'No se pudieron cargar artistas');
      if (message.includes('Token invalido') || message.includes('Falta token')) {
        this.cerrarSesion();
      } else {
        this.artistError.set(message);
      }
    } finally {
      this.artistsLoading.set(false);
    }
  }

  protected cancionesResumen(artista: Artista): string {
    if (!artista.canciones || artista.canciones.length === 0) {
      return 'Sin canciones';
    }

    return artista.canciones
      .map((cancion) => {
        const extra: string[] = [];
        if (cancion.album) {
          extra.push(cancion.album);
        }
        if (cancion.anio_lanzamiento) {
          extra.push(String(cancion.anio_lanzamiento));
        }
        return extra.length > 0 ? `${cancion.titulo} (${extra.join(' / ')})` : cancion.titulo;
      })
      .join(', ');
  }

  private restoreSession(): void {
    const savedToken = localStorage.getItem('musica_token');
    if (!savedToken) {
      return;
    }

    this.token = savedToken;
    this.isLoggedIn.set(true);
    void this.cargarUsuarios();
    void this.cargarArtistas();
  }

  private authHeaders(): HttpHeaders {
    return new HttpHeaders({
      Authorization: `Bearer ${this.token}`,
    });
  }

  private safeText(value: unknown): string {
    if (value === null || value === undefined) {
      return '';
    }
    return String(value).trim();
  }

  private toNullableNumber(value: unknown, min: number, max?: number): number | null {
    const raw = this.safeText(value);
    if (!raw) {
      return null;
    }

    const parsed = Number(raw);
    if (!Number.isFinite(parsed)) {
      return null;
    }

    const intValue = Math.trunc(parsed);
    if (intValue < min) {
      return null;
    }
    if (max !== undefined && intValue > max) {
      return null;
    }

    return intValue;
  }

  private readError(error: unknown, fallback: string): string {
    const apiError = error as ApiError;
    const detail = apiError?.error?.detail;
    return typeof detail === 'string' ? detail : fallback;
  }
}
