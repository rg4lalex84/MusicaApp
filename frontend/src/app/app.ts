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

interface Artista {
  id: number;
  nombre: string;
  apellido: string;
  genero: string;
  canciones: string[];
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

  protected readonly artistaForm = this.fb.nonNullable.group({
    nombre: ['', Validators.required],
    apellido: ['', Validators.required],
    genero: ['', Validators.required],
    canciones: [''],
  });

  protected readonly isLoggedIn = signal(false);
  protected readonly activeMenu = signal<MenuOption>('usuarios');
  protected readonly showUserModal = signal(false);
  protected readonly showArtistModal = signal(false);
  protected readonly loginLoading = signal(false);
  protected readonly usersLoading = signal(false);
  protected readonly artistsLoading = signal(false);
  protected readonly saveUserLoading = signal(false);
  protected readonly saveArtistLoading = signal(false);
  protected readonly loginError = signal('');
  protected readonly userError = signal('');
  protected readonly artistError = signal('');
  protected readonly usuarios = signal<Usuario[]>([]);
  protected readonly artistas = signal<Artista[]>([]);
  protected readonly editingArtistaId = signal<number | null>(null);

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
    this.showArtistModal.set(false);
    this.editingArtistaId.set(null);
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

  protected abrirPopupUsuario(): void {
    this.usuarioForm.reset({
      usuario: '',
      nombre: '',
      apellido: '',
      password: '',
    });
    this.userError.set('');
    this.showArtistModal.set(false);
    this.showUserModal.set(true);
  }

  protected cerrarPopupUsuario(): void {
    this.showUserModal.set(false);
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
      const body = this.usuarioForm.getRawValue();
      await firstValueFrom(
        this.http.post<Usuario>(`${AUTH_API}/usuarios`, body, {
          headers: this.authHeaders(),
        }),
      );

      this.showUserModal.set(false);
      await this.cargarUsuarios();
    } catch (error) {
      this.userError.set(this.readError(error, 'No se pudo guardar el usuario'));
    } finally {
      this.saveUserLoading.set(false);
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
        genero: artista.genero,
        canciones: artista.canciones.join(', '),
      });
    } else {
      this.editingArtistaId.set(null);
      this.artistaForm.reset({
        nombre: '',
        apellido: '',
        genero: '',
        canciones: '',
      });
    }

    this.artistError.set('');
    this.showUserModal.set(false);
    this.showArtistModal.set(true);
  }

  protected cerrarPopupArtista(): void {
    this.showArtistModal.set(false);
    this.editingArtistaId.set(null);
    this.artistError.set('');
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
        genero: formValue.genero,
        canciones: this.parseCanciones(formValue.canciones),
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
      `Quieres eliminar al artista ${artista.nombre} ${artista.apellido}?`,
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

  private parseCanciones(value: string): string[] {
    return value
      .split(',')
      .map((item) => item.trim())
      .filter((item) => item.length > 0);
  }

  private readError(error: unknown, fallback: string): string {
    const apiError = error as ApiError;
    const detail = apiError?.error?.detail;
    return typeof detail === 'string' ? detail : fallback;
  }
}
