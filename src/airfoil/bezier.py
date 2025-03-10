import src.airfoil.helpers as aux
import numpy as np
import matplotlib.pyplot as plt
import neuralfoil as nf
from pandas import read_csv
from scipy.signal import resample
from xfoil import run_xfoil, plot_polar

"""
Baseado em https://stackoverflow.com/questions/12643079/b%C3%A9zier-curve-fitting-with-scipy
e provavelmente na tese de Tim Andrew Pastva, "Bézier Curve Fitting", 1998.

Outros materiais:
Geometric Modeling - Mortenson
Innovative Design and Development Practices in Aerospace and Automotive Engineering - Pg.  79
"""


class bezier_airfoil:

    def __init__(self):
        """Para debug"""
        self.sim = False  # Informa se o perfil já foi simulado

    def set_coords_from_dat(self, airfoil_path: str):
        """Converte o .dat para coordenadas np.array X e Y"""
        self.airfoil_path = airfoil_path
        df = read_csv(airfoil_path, names=("X", "Y"), sep="\s+")
        self.name = df.iloc[0]["X"]
        self.X = df["X"].drop(0).to_numpy(float)
        self.Y = df["Y"].drop(0).to_numpy(float)
        self.X_upper = self.X[: int(len(self.X) / 2)]
        self.X_lower = self.X[int(len(self.X) / 2) :]
        self.Y_upper = self.Y[: int(len(self.Y) / 2)]
        self.Y_lower = self.Y[int(len(self.Y) / 2) :]

    def set_genome_points(self, coords_upper: list, coords_lower: list):
        self.cp_upper = coords_upper
        self.cp_lower = coords_lower

    def set_X_upper(self, xvalue):
        self.X_upper = xvalue

    def set_X_lower(self, xvalue):
        self.X_lower = xvalue

    def set_Y_upper(self, yvalue):
        self.Y_upper = yvalue

    def set_Y_lower(self, yvalue):
        self.Y_lower = yvalue

    def set_name(self, name):
        self.name = name

    def set_fitness(self, fitness):
        self.fitness = fitness

    def set_shape_from_cp(self):
        if self.cp_upper == None or self.cp_lower == None:
            raise Exception("You must set the control points before setting shape.")

        X_bezier_upper, Y_bezier_upper = aux.generate_bezier_curve(self.cp_upper)
        X_bezier_lower, Y_bezier_lower = aux.generate_bezier_curve(self.cp_lower)

        self.X_lower = X_bezier_lower
        self.X_upper = X_bezier_upper
        self.Y_lower = Y_bezier_lower
        self.Y_upper = Y_bezier_upper

    def get_bezier_cp(self, degree_upper: int, degree_lower: int):
        """
        Calcula os parâmetros de bezier.

        Recebe graus diferentes para o intra e extradorso já que
        para perfis arqueados, o intradorso necessita de mais pontos que o
        extradorso, assim, pode-se diminuir a quantidade de pontos totais
        e melhorar a velocidade de convergência do algoritmo otimizador.
        """

        self.degree_upper = degree_upper
        self.degree_lower = degree_lower

        if (self.degree_upper or self.degree_lower) < 1:
            raise ValueError("Grau precisa ser 1 ou maior.")

        if len(self.X) != len(self.Y):
            raise ValueError("X e Y precisam ter o mesmo tamanho.")

        if len(self.X) < (self.degree_lower + 1 or self.degree_upper + 1):
            raise ValueError(
                f"É necessário ter pelo menos {self.degree + 1} pontos para "
                f"determinar os parâmetros de uma curva de grau {self.degree}. "
                f"Foram dados apenas {len(self.X)} pontos."
            )

        T = np.linspace(0, 1, len(self.X_upper))
        M_upper = aux.bmatrix(T, self.degree_upper)
        points_upper = np.array(list(zip(self.X_upper, self.Y_upper)))
        points_lower = np.array(list(zip(self.X_lower, self.Y_lower)))

        cp_upper = aux.least_square_fit(points_upper, M_upper).tolist()
        cp_upper[0] = [self.X_upper[0], self.Y_upper[0]]
        cp_upper[len(cp_upper) - 1] = [
            self.X_upper[len(self.X_upper) - 1],
            self.Y_upper[len(self.Y_upper) - 1],
        ]

        M_lower = aux.bmatrix(T, self.degree_lower)
        cp_lower = aux.least_square_fit(points_lower, M_lower).tolist()
        cp_lower[0] = [self.X_lower[0], self.Y_lower[0]]
        cp_lower[len(cp_lower) - 1] = [
            self.X_lower[len(self.X_lower) - 1],
            self.Y_lower[len(self.Y_lower) - 1],
        ]

        self.cp_upper = cp_upper
        self.cp_lower = cp_lower
        return self.cp_upper, self.cp_lower

    def simulate_xfoil(
        self,
        airfoil_path: str,
        name: str,
        alpha_i=0,
        alpha_f=10,
        alpha_step=0.25,
        Re=1000000,
        n_iter=100,
        polar_path="src/xfoil_runner/data/genome_polar.txt",
        min_points_to_converged=20,
    ):
        """Roda simulação pelo XFOIL"""
        run_xfoil(
            airfoil_path,
            name,
            alpha_i,
            alpha_f,
            alpha_step,
            Re,
            n_iter,
            polar_path=polar_path,
        )
        self.sim = True

        with open(polar_path) as file:
            """Ref: https://github.com/ashokolarov/Genetic-airfoil"""
            polar_data = np.array(
                [
                    np.array([float(x) for x in line.split()])
                    for line in file.readlines()[12:]
                ]
            )

            """Descarta os perfis que não convergirem"""
            try:
                alpha = polar_data[:, 0]
                if len(alpha) < min_points_to_converged:
                    self.converged = False
                else:
                    Cl = polar_data[:, 1]
                    Cd = polar_data[:, 2]
                    self.converged = (
                        True  # Estado que determina se o perfil convergiu na análise
                    )

                    Cl_integration = np.trapz(Cl, alpha)
                    Cd_integration = np.trapz(Cd, alpha)
                    Cl_max = max(Cl)
                    ClCd = Cl / Cd
                    ClCd_integration = np.trapz(ClCd, alpha)
                    Cl3Cd2 = (Cl) ** 3 / (Cd) ** 2
                    ClCd_max = max(ClCd)
                    Cl3Cd2_max = max(Cl3Cd2)

                    stall_angle = alpha[np.argmax(Cl)]

                    self.alpha = alpha
                    self.Cl = Cl
                    self.Cd = Cd
                    self.Cl_integration = Cl_integration
                    self.Cd_integration = Cd_integration
                    self.ClCd_integration = ClCd_integration
                    self.Cl_max = Cl_max
                    self.ClCd_max = ClCd_max
                    self.Cl3Cd2_max = Cl3Cd2_max
                    self.stall_angle = stall_angle
            except:
                self.converged = False

    def simulate_neuralfoil(
        self,
        airfoil_path: str,
        alpha_i=0,
        alpha_f=10,
        alpha_step=0.25,
        Re=1000000,
        model_size="xlarge",
    ):
        simulation = nf.get_aero_from_dat_file(
            filename=airfoil_path,
            alpha=np.arange(alpha_i, alpha_f + alpha_step, alpha_step),
            Re=Re,
            model_size=model_size,
        )
        alpha = np.arange(alpha_i, alpha_f + alpha_step, alpha_step)
        Cl = simulation["CL"]
        Cd = simulation["CD"]
        Cm = simulation["CM"]
        confidence = simulation["analysis_confidence"]

        Cl_integration = np.trapz(Cl, alpha)
        Cd_integration = np.trapz(Cd, alpha)
        Cl_max = max(Cl)
        ClCd = Cl / Cd
        ClCd_integration = np.trapz(ClCd, alpha)
        Cl3Cd2 = (Cl) ** 3 / (Cd) ** 2
        ClCd_max = max(ClCd)
        Cl3Cd2_max = max(Cl3Cd2)

        stall_angle = alpha[np.argmax(Cl)]

        self.alpha = alpha
        self.Cl = Cl
        self.Cd = Cd
        self.Cl_integration = Cl_integration
        self.Cd_integration = Cd_integration
        self.ClCd_integration = ClCd_integration
        self.Cl_max = Cl_max
        self.ClCd_max = ClCd_max
        self.Cl3Cd2_max = Cl3Cd2_max
        self.stall_angle = stall_angle

        def is_array_below(array1, array2):
            # Ensure both arrays have the same length
            if len(array1) != len(array2):
                raise Exception("The arrays must have the same length.")

            # Check each element
            for a, b in zip(array1, array2):
                if a >= b:
                    return False

            return True

        if is_array_below(self.Y_lower, self.Y_upper):
            self.converged = True
        else:
            self.converged = False

        self.sim = True

    def get_opt_params(
        self,
        polar_path="src/xfoil_runner/data/genome_polar.txt",
        min_points_to_converged=20,
    ):

        if not self.sim:
            raise ValueError("O perfil precisa ser simulado antes")

        with open(polar_path) as file:
            """Ref: https://github.com/ashokolarov/Genetic-airfoil"""
            polar_data = np.array(
                [
                    np.array([float(x) for x in line.split()])
                    for line in file.readlines()[12:]
                ]
            )

            """Descarta os perfis que não convergirem"""
            try:
                alpha = polar_data[:, 0]
                if len(alpha) < min_points_to_converged:
                    self.converged = False
                else:
                    Cl = polar_data[:, 1]
                    Cd = polar_data[:, 2]
                    self.converged = (
                        True  # Estado que determina se o perfil convergiu na análise
                    )

                    Cl_integration = np.trapz(Cl, alpha)
                    Cd_integration = np.trapz(Cd, alpha)
                    Cl_max = max(Cl)
                    ClCd = Cl / Cd
                    ClCd_integration = np.trapz(ClCd, alpha)
                    Cl3Cd2 = (Cl) ** 3 / (Cd) ** 2
                    ClCd_max = max(ClCd)
                    Cl3Cd2_max = max(Cl3Cd2)

                    stall_angle = alpha[np.argmax(Cl)]

                    self.alpha = alpha
                    self.Cl = Cl
                    self.Cd = Cd
                    self.Cl_integration = Cl_integration
                    self.Cd_integration = Cd_integration
                    self.ClCd_integration = ClCd_integration
                    self.Cl_max = Cl_max
                    self.ClCd_max = ClCd_max
                    self.Cl3Cd2_max = Cl3Cd2_max
                    self.stall_angle = stall_angle
            except:
                self.converged = False


def _example():
    genome = bezier_airfoil()
    genome.set_coords_from_dat("airfoils/results/08_07_2024_15h41m14s/genome_0.dat")
    # genome.simulate_xfoil("airfoils/soutoFoil.dat",
    #                 "soutoFoil", alpha_f=15.5, alpha_step=0.5, Re=100000, polar_path="src/xfoil_runner/data/genome_polar.txt")

    genome.simulate_neuralfoil(
        "airfoils/results/08_07_2024_15h41m14s/genome_0.dat",
        alpha_f=15.5,
        alpha_step=0.5,
        Re=100000,
    )

    initial_airfoil = bezier_airfoil()
    initial_airfoil.set_coords_from_dat("airfoils/e216.dat")
    initial_airfoil.simulate_neuralfoil(
        "airfoils/e216.dat", alpha_f=15.5, alpha_step=0.5, Re=100000
    )
    print(initial_airfoil.ClCd_max, " ", genome.ClCd_max)

    # fig, axs = plt.subplots(2, 2)
    # plot_polar(axs, "src/xfoil_runner/data/initial_polar.txt")
    # plot_polar_neuralfoil(axs, genome, np.arange(0, 16, 0.5))

    # airfoil.set_X(np.linspace(0, 15))
    # airfoil.set_Y(np.cos(np.linspace(0, 15)))

    plt.figure(figsize=(9, 3))

    plt.plot(genome.X_upper, genome.Y_upper, "r", label=genome.name)
    plt.plot(genome.X_lower, genome.Y_lower, "r")

    plt.plot(
        initial_airfoil.X_upper,
        initial_airfoil.Y_upper,
        "b",
        label=initial_airfoil.name,
    )
    plt.plot(initial_airfoil.X_lower, initial_airfoil.Y_lower, "b")

    cp_upper, cp_lower = genome.get_bezier_cp(8, 16)  # Args: Grau do polinômio
    # cp_lower[7] = [cp_lower[7][0]+0.1, cp_lower[7][1]]

    """Gera listas com os pontos de controle"""
    x_cp_list_upper = [i[0] for i in cp_upper]
    y_cp_list_upper = [i[1] for i in cp_upper]
    x_cp_list_lower = [i[0] for i in cp_lower]
    y_cp_list_lower = [i[1] for i in cp_lower]

    """Converte a lista para array"""
    x_cp_upper = np.array(x_cp_list_upper)
    y_cp_upper = np.array(y_cp_list_upper)
    x_cp_lower = np.array(x_cp_list_lower)
    y_cp_lower = np.array(y_cp_list_lower)

    """Plota pontos de controle"""
    # plt.plot(x_cp_upper, y_cp_upper, 'k--o', label='Control Points - Upper')
    # plt.plot(x_cp_lower, y_cp_lower, 'k--o')

    """Plota a curva de bezier"""
    X_bezier_upper, Y_bezier_upper = aux.generate_bezier_curve(
        cp_upper, nTimes=len(genome.X_upper)
    )
    # plt.plot(X_bezier_upper, Y_bezier_upper, 'g--', label='Bezier')

    X_bezier_lower, Y_bezier_lower = aux.generate_bezier_curve(
        cp_lower, nTimes=len(genome.X_lower)
    )
    # plt.plot(X_bezier_lower, Y_bezier_lower, 'g--', label='Bezier')

    X_bezier = np.concatenate((X_bezier_upper, X_bezier_lower))
    Y_bezier = np.concatenate((Y_bezier_upper, Y_bezier_lower))
    # plt.plot(X_bezier, Y_bezier, 'g--', label='Bezier')

    plt.legend()
    plt.xlabel("x/c")
    # plt.ylabel("y")

    """Calcula o erro - PRECISA SER MELHORADO (Ver o artigo)"""
    Y_error = np.abs(Y_bezier_lower - resample(genome.Y_lower, len(Y_bezier_lower)))
    print(f"Erro máximo (Curva inferior): {max(Y_error)}")
    # plt.figure()
    # plt.plot(X_bezier_lower, Y_error, 'g--', label="Erro")
    # plt.title("Erro em Y (Curva inferior)")
    # plt.xlabel("x/c")

    plt.show()


# Se esse arquivo for executado, rode _example()
if __name__ == "__main__":
    _example()
