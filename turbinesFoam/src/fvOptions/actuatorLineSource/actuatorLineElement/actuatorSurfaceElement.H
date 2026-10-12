/*---------------------------------------------------------------------------*\
  =========                 |
  \\      /  F ield         | OpenFOAM: The Open Source CFD Toolbox
   \\    /   O peration     |
    \\  /    A nd           | Copyright held by original author(s)
     \\/     M anipulation  |
-------------------------------------------------------------------------------
License
    This file is part of turbinesFoam, which is based on OpenFOAM.

    OpenFOAM is free software: you can redistribute it and/or modify it
    under the terms of the GNU General Public License as published by
    the Free Software Foundation, either version 3 of the License, or
    (at your option) any later version.

    OpenFOAM is distributed in the hope that it will be useful, but WITHOUT
    ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or
    FITNESS FOR A PARTICULAR PURPOSE.  See the GNU General Public License
    for more details.

    You should have received a copy of the GNU General Public License
    along with OpenFOAM.  If not, see <http://www.gnu.org/licenses/>.

Class
    Foam::fv::actuatorSurfaceElement

Description
    An actuator surface element: an actuator line element that averages the
    inflow velocity over \c nChordwise equal chord strips and distributes the
    aerodynamic force uniformly across those strips (Yang & Sotiropoulos,
    arXiv:1702.02108v4, Sec. 2.1), spread with a spherical Gaussian kernel
    whose width is mesh-based (Massie, Ouro, Stoesser & Luo, Energies 2019;
    this element keeps their mesh branch 4*cbrt(V) at the default meshFactor
    and drops the c/4 branch). A hybrid of the two, not either paper's model.

    The blade element momentum force chain -- coefficient lookup, dynamic
    stall, added mass, end effects, and CSV output -- is inherited unchanged
    from \c actuatorLineElement; only inflow sampling, force projection, and
    projection width differ.

SourceFiles
    actuatorSurfaceElement.C

\*---------------------------------------------------------------------------*/

#ifndef actuatorSurfaceElement_H
#define actuatorSurfaceElement_H

#include "actuatorLineElement.H"

// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //

namespace Foam
{
namespace fv
{

/*---------------------------------------------------------------------------*\
                        Class actuatorSurfaceElement Declaration
\*---------------------------------------------------------------------------*/

class actuatorSurfaceElement
:
    public actuatorLineElement
{

protected:

    // Protected data

        //- Number of chordwise strips used for inflow averaging and force
        //  distribution
        label nChordwise_;


    // Protected Member Functions

        //- Return the midpoint of chord strip k, located at
        //  X_k = position_ + (chordMount_ - (k + 0.5)/nChordwise_) * c *
        //  unit(chordDirection_)
        vector chordPoint(label k) const;

        //- Calculate projection width from the mesh only
        scalar calcProjectionEpsilon() override;

        //- Apply force field based on force vector, distributed uniformly
        //  over the chord strips
        void applyForceField(volVectorField& forceField) override;

        //- Get chord-averaged inflow velocity
        void calculateInflowVelocity(const volVectorField& Uin) override;


public:

    //- Runtime type information
    TypeName("actuatorSurfaceElement");


    // Static Member Functions

        //- Return the cell-loop prefilter box of a chord line: the bounding
        //  box of the segment a-b grown by projectionRadius metres in every
        //  direction. A cell outside it is farther than projectionRadius
        //  from every chord point, where the Gaussian kernel is already
        //  below exp(-ln(1000)) of its peak
        static boundBox chordPrefilterBox
        (
            const point& a,
            const point& b,
            const scalar projectionRadius
        );


    //- Constructor
    actuatorSurfaceElement
    (
        const word& name,
        const dictionary& dict,
        const fvMesh& mesh
    );


    //- Destructor
    virtual ~actuatorSurfaceElement();


};


// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //

} // End namespace fv
} // End namespace Foam

// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //

#endif

// ************************************************************************* //